// sht31.h -- CRC dan konversi data SHT31 (suhu & kelembapan). Portabel & teruji di komputer.
//
// Perintah pengukuran: 0x24 0x00 ke alamat I2C 0x44 (repeatability tinggi, tanpa clock stretching).
// Balasan 6 byte: suhu(2) crc | kelembapan(2) crc.   CRC-8: polinomial 0x31, awal 0xFF.
#pragma once
#include <stdint.h>

namespace purifier {

inline uint8_t sht31_crc8(const uint8_t* d, int n) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < n; ++i) {
    crc ^= d[i];
    for (int b = 0; b < 8; ++b) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
  }
  return crc;
}

// Mengembalikan true bila kedua CRC cocok.
inline bool sht31_parse(const uint8_t b[6], double& temp_c, double& rh) {
  if (sht31_crc8(b, 2) != b[2] || sht31_crc8(b + 3, 2) != b[5]) return false;
  const uint16_t t = (uint16_t)((b[0] << 8) | b[1]);
  const uint16_t h = (uint16_t)((b[3] << 8) | b[4]);
  temp_c = -45.0 + 175.0 * t / 65535.0;
  rh = 100.0 * h / 65535.0;
  return true;
}

}  // namespace purifier
