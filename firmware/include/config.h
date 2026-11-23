// config.h -- pin, konstanta, dan mode build. Papan: ESP32-S3-DevKitC-1.
//
// Mode:
//   SIM_ANALOG=0 (bawaan)  sensor sungguhan: PMS5003 (UART) + SHT31 (I2C), kontrol tiap 60 detik.
//   SIM_ANALOG=1           mode simulasi (mis. Wokwi): PM2.5 & RH dari dua potensiometer,
//                          1 detik nyata = 1 menit simulasi supaya hold-timer 15 menit bisa dilihat.
#pragma once
#include <stdint.h>

#ifndef SIM_ANALOG
#define SIM_ANALOG 0
#endif

// ---- Pin (hindari pin strapping 0/3/45/46, USB 19/20, flash/PSRAM) ----
constexpr int PIN_PMS_RX = 16;      // <- TX PMS5003
constexpr int PIN_PMS_TX = 17;      // -> RX PMS5003
constexpr int PIN_SDA = 8;          // SHT31
constexpr int PIN_SCL = 9;
constexpr int PIN_FAN_PWM = 4;      // -> kabel PWM kipas 4-pin (25 kHz)
constexpr int PIN_FAN_EN = 5;       // -> modul saklar daya kipas (HIGH = kipas dapat daya)
constexpr int PIN_TACH = 6;         // <- kabel tacho kipas (open-collector, pull-up)
constexpr int PIN_LED_LOW = 10;
constexpr int PIN_LED_MED = 11;
constexpr int PIN_LED_TURBO = 12;
constexpr int PIN_LED_FAULT = 13;
constexpr int PIN_BTN_PROFILE = 14; // tombol ke GND: ganti profil normal <-> rentan
constexpr int PIN_POT_PM = 1;       // hanya mode SIM_ANALOG
constexpr int PIN_POT_RH = 2;       // hanya mode SIM_ANALOG

// ---- Kipas ----
constexpr int PWM_FREQ = 25000;     // Hz, standar kipas PC 4-pin
constexpr int PWM_BITS = 8;
constexpr int PWM_CHANNEL = 0;      // hanya dipakai di Arduino-ESP32 2.x
constexpr double SPEED[4] = {0.0, 0.3, 0.6, 1.0};  // fraksi kecepatan OFF/LOW/MEDIUM/TURBO
constexpr double VULN_FACTOR = 0.6; // pengali ambang profil rentan

// ---- Waktu & fail-safe ----
#if SIM_ANALOG
constexpr uint32_t TICK_MS = 1000;  // 1 detik nyata = 1 menit simulasi
#else
constexpr uint32_t TICK_MS = 60000; // satu langkah kontrol per menit (sama dengan simulator)
#endif
constexpr double DT_MIN = 1.0;      // lebar langkah kontrol dalam menit (sama dengan simulator)
constexpr int PM_FAULT_LIMIT = 5;   // tanpa data PM2.5 selama 5 langkah -> fail-safe MEDIUM
constexpr int FAN_FAULT_LIMIT = 3;  // kipas diperintah tapi RPM ~0 selama 3 langkah -> tandai gangguan
constexpr double MIN_RPM = 100.0;
#if SIM_ANALOG
constexpr bool TACH_ENABLED = false;
#else
constexpr bool TACH_ENABLED = true; // set false bila kipas tidak punya kabel tacho
#endif
constexpr uint8_t SHT31_ADDR = 0x44;
