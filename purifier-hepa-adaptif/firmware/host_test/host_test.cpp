// host_test.cpp -- uji logika firmware di KOMPUTER (tanpa ESP32).
//
// Membandingkan controller.h / pms5003.h / sht31.h dengan vektor yang dibangkitkan simulator Python
// (tools/gen_vectors.py). Jalankan: make test-firmware
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "controller.h"
#include "pms5003.h"
#include "sht31.h"

using namespace purifier;

static int g_fail = 0, g_checks = 0;
#define CHECK(cond, ...)                                  \
  do {                                                    \
    ++g_checks;                                           \
    if (!(cond)) {                                        \
      ++g_fail;                                           \
      std::printf("  [GAGAL] " __VA_ARGS__);              \
      std::printf("\n");                                  \
    }                                                     \
  } while (0)

static std::vector<std::vector<double>> read_csv(const std::string& path) {
  std::vector<std::vector<double>> rows;
  std::ifstream in(path);
  if (!in) {
    std::printf("  [GAGAL] tidak bisa membuka %s (jalankan: make test-firmware)\n", path.c_str());
    ++g_fail;
    return rows;
  }
  std::string line;
  std::getline(in, line);  // header
  while (std::getline(in, line)) {
    if (line.empty()) continue;
    std::vector<double> r;
    std::stringstream ss(line);
    std::string cell;
    while (std::getline(ss, cell, ',')) r.push_back(std::strtod(cell.c_str(), nullptr));
    rows.push_back(r);
  }
  return rows;
}

static bool close_rel(double a, double b, double tol) {
  return std::fabs(a - b) <= tol * (1.0 + std::fabs(b));
}

static void test_decide(const std::string& dir) {
  const auto rows = read_csv(dir + "/decide.csv");
  Config cfg;
  int bad = 0;
  for (const auto& r : rows) {  // pm_f,f,level,since,new_level,new_since
    double since = r[3];
    const int nl = decide_level(r[0], r[1], (int)r[2], since, 1.0, cfg);
    if (nl != (int)r[4] || !close_rel(since, r[5], 1e-12)) {
      if (bad++ < 3) std::printf("    beda: pm=%.6g f=%.2f lvl=%d since=%.0f -> %d (harap %d)\n", r[0], r[1], (int)r[2], r[3], nl, (int)r[4]);
    }
  }
  CHECK(!rows.empty() && bad == 0, "decide_level: %d dari %zu kasus berbeda dari Python", bad, rows.size());
  std::printf("  decide_level  : %zu kasus acak\n", rows.size());
}

static void test_correct(const std::string& dir) {
  const auto rows = read_csv(dir + "/correct.csv");
  Config cfg;
  int bad = 0;
  for (const auto& r : rows) {  // raw,rh,expected
    const double v = firmware_correct(r[0], r[1], cfg.kappa_est, cfg.smoke_est);
    if (!close_rel(v, r[2], 1e-12)) ++bad;
  }
  CHECK(!rows.empty() && bad == 0, "firmware_correct: %d dari %zu kasus berbeda dari Python", bad, rows.size());
  std::printf("  firmware_corr : %zu kasus acak\n", rows.size());
}

static void test_sequence(const std::string& dir, const char* file, double f) {
  const auto rows = read_csv(dir + "/" + file);
  std::ifstream init(dir + "/seq_init.txt");
  double pm0 = 0.0;
  init >> pm0;
  Controller c;
  c.cfg.f_profile = f;
  c.seed(pm0);
  int bad_lvl = 0, bad_pm = 0, changes = 0, prev = 0;
  for (const auto& r : rows) {  // raw,rh,pm_f,level
    c.step(r[0], r[1], 1.0);
    if (c.level != (int)r[3]) ++bad_lvl;
    if (!close_rel(c.pm_f, r[2], 1e-9)) ++bad_pm;
    if (c.level != prev) ++changes;
    prev = c.level;
  }
  CHECK(!rows.empty() && bad_lvl == 0 && bad_pm == 0, "%s: level beda %d, pm_f beda %d dari %zu langkah", file, bad_lvl, bad_pm, rows.size());
  std::printf("  %-14s: %zu menit, %d pergantian level, semua sama dengan Python\n", file, rows.size(), changes);
}

static void test_pms5003() {
  uint8_t fr[32] = {0x42, 0x4D, 0x00, 0x1C};
  auto put = [&](int i, uint16_t v) { fr[i] = (uint8_t)(v >> 8); fr[i + 1] = (uint8_t)(v & 0xFF); };
  put(4, 12); put(6, 34); put(8, 56); put(10, 10); put(12, 30); put(14, 50);
  uint16_t sum = 0;
  for (int i = 0; i < 30; ++i) sum = (uint16_t)(sum + fr[i]);
  put(30, sum);

  Pms5003Parser p;
  Pms5003Frame out{};
  bool got = false;
  const uint8_t junk[] = {0x00, 0x42, 0x13, 0x42, 0x42};  // sampah + 0x42 palsu: harus sinkron ulang
  for (uint8_t b : junk) got = p.feed(b, out) || got;
  CHECK(!got, "sampah tidak boleh menghasilkan frame");
  for (int i = 0; i < 32; ++i) got = p.feed(fr[i], out) || got;
  CHECK(got && out.pm25_cf1 == 34 && out.pm1_cf1 == 12 && out.pm10_cf1 == 56 && out.pm25_atm == 30, "parser PMS5003: nilai frame salah");

  fr[20] ^= 0x01;  // rusak satu bit -> checksum harus menolak
  Pms5003Parser q;
  bool bad = false;
  for (int i = 0; i < 32; ++i) bad = q.feed(fr[i], out) || bad;
  CHECK(!bad, "frame dengan checksum salah harus ditolak");
  std::printf("  PMS5003       : parser, sinkron ulang, tolak checksum salah\n");
}

static void test_sht31() {
  const uint8_t beef[2] = {0xBE, 0xEF};
  CHECK(sht31_crc8(beef, 2) == 0x92, "CRC8 contoh datasheet Sensirion (0xBEEF -> 0x92)");
  uint8_t b[6] = {0x66, 0x66, 0, 0x80, 0x00, 0};
  b[2] = sht31_crc8(b, 2);
  b[5] = sht31_crc8(b + 3, 2);
  double t = 0, rh = 0;
  CHECK(sht31_parse(b, t, rh), "parse SHT31 valid");
  CHECK(std::fabs(t - 25.0) < 1e-3 && std::fabs(rh - 50.0) < 0.01, "konversi suhu 25 C / RH 50%% (t=%.3f rh=%.3f)", t, rh);
  b[2] ^= 0xFF;
  CHECK(!sht31_parse(b, t, rh), "CRC salah harus ditolak");
  std::printf("  SHT31         : CRC8, konversi, tolak CRC salah\n");
}

static void test_misc() {
  Controller c;
  c.step(200.0, 60.0, 1.0);  // inisialisasi pm_f dari bacaan pertama
  CHECK(c.pm_init && c.level >= LVL_LOW, "bacaan pertama tinggi harus langsung menaikkan level");
  c.force_level(LVL_MEDIUM);
  CHECK(c.level == LVL_MEDIUM && c.since_min == 0.0, "force_level (fail-safe)");
  CHECK(humidity_growth(99.0, 0.15) == humidity_growth(90.0, 0.15), "RH dibatasi 90%%");
  std::printf("  lain-lain     : inisialisasi, fail-safe, batas RH\n");
}

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "firmware/host_test/vectors";
  std::printf("== Uji firmware di komputer vs simulator Python ==\n");
  test_decide(dir);
  test_correct(dir);
  test_sequence(dir, "seq_f1.csv", 1.0);
  test_sequence(dir, "seq_f06.csv", 0.6);
  test_pms5003();
  test_sht31();
  test_misc();
  std::printf("== %d pemeriksaan, %d gagal ==\n", g_checks, g_fail);
  return g_fail == 0 ? 0 : 1;
}
