# Firmware unit utama (ESP32-S3)

> **Status:** logika kontrol (`include/controller.h`), parser PMS5003 (`pms5003.h`) dan helper SHT31 (`sht31.h`) **sudah diuji di komputer** terhadap simulator Python (`make test-firmware`). Lapisan Arduino (`src/main.cpp`: UART, I2C, PWM, tacho, tombol) **belum diuji di perangkat keras atau Wokwi**. Hanya sintaksnya yang diperiksa terhadap header Arduino tiruan. Anggap build pertamamu sebagai tahap pengujian.
>
> **Belum ada:** firmware wearable (klip jari nRF52840) dan penerima BLE di unit utama. Urutan yang disarankan: purifier berbasis PM2.5 dulu, lalu wearable dalam mode *logging* saja, baru fusi sensor.

## Isi

| Berkas | Fungsi | Teruji di komputer |
|---|---|---|
| `include/controller.h` | Koreksi RH + asap, EMA, state machine 4 level, fail-safe | Ya (8.000 kasus acak + 2 × 11.520 menit) |
| `include/pms5003.h` | Parser frame UART 32 byte | Ya |
| `include/sht31.h` | CRC-8 dan konversi suhu/RH | Ya |
| `include/config.h` | Pin, konstanta, mode build | - |
| `src/main.cpp` | Loop utama: sensor → kontrol → kipas, log CSV serial | Hanya sintaks |
| `host_test/host_test.cpp` | Uji C++ vs vektor dari Python | - |

## Pin (ESP32-S3-DevKitC-1)

| Fungsi | GPIO | Sambungan |
|---|---|---|
| UART2 RX | 16 | TX PMS5003 |
| UART2 TX | 17 | RX PMS5003 |
| I2C SDA / SCL | 8 / 9 | SHT31 (alamat 0x44) |
| PWM kipas | 4 | Kabel PWM kipas 4-pin (25 kHz) |
| Saklar daya kipas | 5 | Modul saklar/relay (HIGH = kipas dapat daya) |
| Tacho kipas | 6 | Kabel tacho (open-collector; beri pull-up 10 kΩ ke 3,3 V) |
| LED LOW / MEDIUM / TURBO / GANGGUAN | 10 / 11 / 12 / 13 | LED + resistor ke GND |
| Tombol profil rentan | 14 | Tombol ke GND (pull-up internal) |
| Potensiometer PM2.5 / RH | 1 / 2 | Hanya mode `SIM_ANALOG` |

Pin dipilih menghindari pin strapping (0, 3, 45, 46), USB (19, 20), serta flash/PSRAM. Periksa lagi terhadap papan dan modul ESP32-S3 yang kamu pakai.

## Daya dan keselamatan

- Hanya tegangan rendah: **adaptor 12 V DC**. Jangan memakai dimmer/SSR listrik PLN untuk prototipe.
- Kipas mendapat 12 V langsung. ESP32-S3 dan PMS5003 mendapat 5 V dari **penurun tegangan** 12 V → 5 V. SHT31 memakai 3,3 V dari papan.
- Kipas PC 4-pin: sinyal PWM umumnya bisa langsung dari pin ESP32 ke kabel PWM, tetapi **cek datasheet kipas**: ada yang butuh penyesuaian level.
- **Level OFF:** kipas 4-pin pada PWM 0% biasanya tetap berputar pelan. Untuk benar-benar mati, putus daya 12 V dengan **modul saklar sisi atas (high-side) atau relay** di `PIN_FAN_EN`. Penyaklaran sisi bawah (low-side) pada kipas 4-pin umumnya tidak disarankan karena referensi sinyal PWM/tacho ikut mengambang. Jika tidak memasang saklar, abaikan GPIO 5 dan terima bahwa OFF = kecepatan minimum.
- Letakkan sensor PMS5003 di dinding samping, **jauh dari lubang keluar kipas**, supaya yang terbaca udara kamar.
- Pastikan kipas punya *static pressure* cukup untuk mendorong udara melewati filter HEPA.

## Build (PlatformIO)

```bash
cd firmware
pio run -e esp32s3-sensors     # sensor sungguhan (PMS5003 + SHT31)
pio run -e esp32s3-sim         # mode potensiometer (SIM_ANALOG=1)
pio run -e esp32s3-sensors -t upload
pio device monitor
```

`main.cpp` menangani perbedaan API PWM Arduino-ESP32 2.x dan 3.x. Setelah build pertama berhasil, sebaiknya kunci versi `platform` di `platformio.ini`.

## Keluaran serial

Satu baris CSV per langkah kontrol (115200 baud), cocok untuk *logging* data PM2.5 nyata (fase 1 di roadmap):

```
ms,pm_raw,rh,pm_corr,pm_f,level,profil,rpm,gangguan
```

`level`: 0 OFF, 1 LOW, 2 MEDIUM, 3 TURBO. `profil`: 0 normal, 1 rentan (tombol, tersimpan di NVS). `gangguan`: 1 bila sensor debu mati atau kipas macet.

## Mencoba di Wokwi (belum diuji)

Tidak ada `diagram.json` karena nama pin papan di Wokwi belum diverifikasi. Cara manual di <https://wokwi.com>:

1. Buat proyek **ESP32-S3** (Arduino). Salin `config.h`, `controller.h`, `pms5003.h`, `sht31.h`, dan `main.cpp`.
2. Di baris atas `config.h` tulis `#define SIM_ANALOG 1`.
3. Tambahkan 2 potensiometer (sinyal ke GPIO 1 dan 2), 3 LED hijau ke GPIO 10–12 dan 1 LED merah ke GPIO 13 (masing-masing dengan resistor), dan satu tombol dari GPIO 14 ke GND.
4. Jalankan. Di mode ini **1 detik nyata = 1 menit simulasi**, jadi hold-timer 15 menit bisa diamati dalam 15 detik. Putar potensiometer PM2.5 dan lihat LED serta log serial.

## Perilaku yang TIDAK ada di simulator

Fail-safe sensor debu mati (paksa MEDIUM setelah 5 langkah tanpa data) dan deteksi kipas macet lewat tacho adalah tambahan firmware. Keduanya belum disimulasikan maupun diuji.
