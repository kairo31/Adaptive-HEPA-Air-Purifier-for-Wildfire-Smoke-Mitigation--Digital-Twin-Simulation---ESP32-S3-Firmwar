// controller.h -- logika kontrol purifier (state machine 4 level).
//
// PORTABEL: tidak memakai Arduino/ESP-IDF, jadi bisa diuji di komputer (firmware/host_test).
// Ini cermin dari sim/simulator.py: firmware_correct(), decide(), dan kontroler A/B.
// Uji `make test-firmware` membuktikan keputusannya sama persis dengan simulator Python.
#pragma once
#include <math.h>

namespace purifier {

enum Level { LVL_OFF = 0, LVL_LOW = 1, LVL_MEDIUM = 2, LVL_TURBO = 3, N_LEVELS = 4 };

constexpr double RH_CAP = 90.0;  // rumus higroskopis meledak mendekati RH 100% -> RH efektif dibatasi

struct Config {
  double ispu_up[3] = {15.5, 55.4, 150.4};   // batas atas ISPU Baik/Sedang/Tidak Sehat (ug/m3)
  double thr_floor[3] = {10.0, 25.0, 60.0};  // lantai ambang absolut (mencegah kedip di udara bersih)
  double hyst = 0.8;                         // ambang turun = 0,8 x ambang naik
  double hold_down_min = 15.0;               // tahan minimal sebelum TURUN level (naik langsung)
  double ema_pm_min = 5.0;                   // penghalus PM2.5 (menit)
  double kappa_est = 0.15;                   // koreksi kelembapan (asumsi kappa aerosol)
  double smoke_est = 1.5;                    // koreksi bias asap PMS5003
  double f_profile = 1.0;                    // pengali ambang: 1,0 normal; 0,6 profil rentan
};

// Faktor pertumbuhan higroskopis partikel pada kelembapan rh (%).
inline double humidity_growth(double rh, double kappa) {
  const double r = rh < RH_CAP ? rh : RH_CAP;
  return 1.0 + (kappa / 1.65) / (100.0 / r - 1.0);
}

// Koreksi bacaan mentah PMS5003: koreksi RH dulu, lalu koreksi asap.
inline double firmware_correct(double raw, double rh, double kappa_est, double smoke_est) {
  const double x = raw / humidity_growth(rh, kappa_est);
  double w = x / 50.0;
  if (w < 0.0) w = 0.0;
  if (w > 1.0) w = 1.0;
  return x / (1.0 + (smoke_est - 1.0) * w);
}

// Keputusan level. NAIK langsung; TURUN hanya bila di bawah ambang-turun (hysteresis)
// DAN sudah >= hold_down_min menit sejak perubahan terakhir. since_min diperbarui di tempat.
inline int decide_level(double pm_f, double f, int level, double& since_min, double dt_min,
                        const Config& c) {
  int t_up = 0, t_dn = 0;
  for (int i = 0; i < 3; ++i) {
    double up = c.ispu_up[i] * f;
    if (up < c.thr_floor[i]) up = c.thr_floor[i];
    if (pm_f > up) ++t_up;
    if (pm_f > up * c.hyst) ++t_dn;
  }
  int nl = level;
  if (t_up > level) {
    nl = t_up;
  } else if (t_dn < level && since_min >= c.hold_down_min) {
    nl = t_dn;
  }
  since_min = (nl != level) ? 0.0 : since_min + dt_min;
  return nl;
}

struct Controller {
  Config cfg;
  double pm_f = 0.0;       // PM2.5 terkoreksi & terhaluskan
  bool pm_init = false;
  int level = LVL_OFF;
  double since_min = 999.0;

  void seed(double pm0) { pm_f = pm0; pm_init = true; }

  // Satu langkah kontrol. raw_pm = bacaan mentah rata-rata periode ini (ug/m3), rh dalam %.
  void step(double raw_pm, double rh, double dt_min = 1.0) {
    const double corr = firmware_correct(raw_pm, rh, cfg.kappa_est, cfg.smoke_est);
    if (!pm_init) seed(corr);
    pm_f += (1.0 - exp(-dt_min / cfg.ema_pm_min)) * (corr - pm_f);
    level = decide_level(pm_f, cfg.f_profile, level, since_min, dt_min, cfg);
  }

  // Dipakai fail-safe (mis. sensor debu mati): paksa level tertentu.
  void force_level(int l) {
    if (l != level) {
      level = l;
      since_min = 0.0;
    }
  }
};

}  // namespace purifier
