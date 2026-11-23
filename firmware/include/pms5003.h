// pms5003.h -- parser frame UART PMS5003 (32 byte, 9600 baud). Portabel & teruji di komputer.
//
// Frame: 0x42 0x4D | panjang(2)=28 | 13 kata data (big-endian) | checksum(2)
// Kata ke-1..6: PM1.0/2.5/10 (CF=1) lalu PM1.0/2.5/10 (atmosferik). Checksum = jumlah byte 0..29.
#pragma once
#include <stdint.h>

namespace purifier {

struct Pms5003Frame {
  uint16_t pm1_cf1, pm25_cf1, pm10_cf1;
  uint16_t pm1_atm, pm25_atm, pm10_atm;
};

class Pms5003Parser {
 public:
  // Suapkan satu byte. Mengembalikan true bila satu frame VALID baru saja selesai (hasil di out).
  bool feed(uint8_t b, Pms5003Frame& out) {
    if (idx_ == 0) {
      if (b == 0x42) buf_[idx_++] = b;
      return false;
    }
    if (idx_ == 1) {
      if (b == 0x4D) {
        buf_[idx_++] = b;
      } else {
        idx_ = (b == 0x42) ? 1 : 0;  // sinkron ulang; buf_[0] sudah 0x42
      }
      return false;
    }
    buf_[idx_++] = b;
    if (idx_ < 32) return false;
    idx_ = 0;
    if (word(2) != 28) return false;
    uint16_t sum = 0;
    for (int i = 0; i < 30; ++i) sum = (uint16_t)(sum + buf_[i]);
    if (sum != word(30)) return false;
    out.pm1_cf1 = word(4);
    out.pm25_cf1 = word(6);
    out.pm10_cf1 = word(8);
    out.pm1_atm = word(10);
    out.pm25_atm = word(12);
    out.pm10_atm = word(14);
    return true;
  }

 private:
  uint8_t buf_[32] = {0};
  int idx_ = 0;
  uint16_t word(int i) const { return (uint16_t)((buf_[i] << 8) | buf_[i + 1]); }
};

}  // namespace purifier
