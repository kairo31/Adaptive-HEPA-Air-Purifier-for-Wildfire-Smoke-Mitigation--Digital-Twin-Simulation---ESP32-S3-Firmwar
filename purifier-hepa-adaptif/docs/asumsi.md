# Tabel asumsi simulator

Dibangkitkan otomatis dari `sim/params.py` oleh `tools/export_params_md.py`. **Ubah angka di `params.py`, bukan di file ini.**

Nomor sumber `[n]` merujuk ke [referensi.md](referensi.md). `AP` = asumsi pribadi (belum ada sumber langsung, diuji dengan rentang lebar).

## Parameter Monte Carlo

| Parameter | Rentang | Distribusi | Satuan | Sumber | Keyakinan | Catatan |
|---|---|---|---|---|---|---|
| `ach_open` | 1 – 5 | log-seragam | 1/jam | [27][28][29] | sedang | ACH rumah tropis berventilasi (rerata Rumoh Aceh 4,06) |
| `ach_closed` | 0.2 – 2 | log-seragam | 1/jam | [10][11] | tinggi | ACH rumah tertutup/AC (studi empat musim) |
| `pen` | 0.6 – 1 | seragam | - | AP | rendah | faktor penetrasi P |
| `dep` | 0.05 – 1 | log-seragam | 1/jam | [11] | sedang-tinggi | laju deposisi k |
| `src` | 5 – 100 | log-seragam | ug/m3/jam | AP | rendah | sumber dalam ruang S/V; hanya aktif pada 30% run (tipikal ~0) |
| `vol` | 30 – 45 | seragam | m3 | AP | rendah | volume kamar |
| `cadr_rated` | 100 – 400 | seragam | m3/jam | [39][40] | tinggi | smoke CADR label |
| `cadr_eff` | 0.33 – 1 | seragam | - | [42] | sedang | CADR efektif / CADR lab (mixing, pintu terbuka) |
| `pm_base` | 5 – 20 | seragam | ug/m3 | AP | rendah | PM2.5 latar sebelum episode |
| `pm_peak` | 50 – 500 | log-seragam | ug/m3 | [13][35] | sedang | puncak plateau episode (tabel: 35-700+; dipersempit utk stabilitas) |
| `ep_start_d` | 1 – 1.5 | seragam | hari | desain | - | episode mulai (hari ke-0 = kalibrasi baseline) |
| `ep_dur_d` | 3 – 5 | seragam | hari | AP | rendah | durasi plateau (tabel: 3-7, rentang 1-14; dipersempit agar muat jendela 8 hari) |
| `ep_rampup_d` | 0.3 – 1 | seragam | hari | AP | rendah | waktu naik |
| `ep_rampdn_d` | 0.5 – 1.5 | seragam | hari | AP | rendah | waktu turun |
| `rh_mean` | 70 – 90 | seragam | %RH | AP+[19] | rendah-sedang | RH rerata tropis |
| `kappa` | 0.05 – 0.2 | seragam | - | AP+[17][18] | sedang | kappa higroskopis aerosol SEBENARNYA (firmware menganggap 0,15). Rentang dipilih agar bias tanpa koreksi pada RH 75-90% ~ +30..+110%, konsisten dgn [16] (hingga +90%) |
| `smoke_bias` | 1.2 – 2 | seragam | x | [16] | sedang-tinggi | PMS5003 membaca berlebih saat asap; dikalikan efek RH (dianggap independen -> galat gabungan tanpa koreksi mungkin berlebihan) |
| `spo2_bias` | 0.3 – 1.3 | seragam | poin | [23][24][25] | tinggi | bias positif (pigmentasi sedang-gelap) |
| `spo2_sigma` | 1 – 3 | seragam | poin | [20][21][23]+AP | rendah-sedang | simpangan baku galat SpO2 per sampel (Arms 3-4% dari bias + ini) |
| `bio_dropout` | 0.05 – 0.2 | seragam | - | AP+[20] | rendah | porsi sampel dibuang (SQI buruk) |
| `hr_sleep_dip` | 0.05 – 0.2 | seragam | - | [31][32]+AP | sedang(arah)/rendah(besaran) | penurunan HR NREM relatif terhadap HR bangun |

## Skenario respons biometrik

`eff_spo2` / `eff_hr` = besar respons pada paparan acuan 150 µg/m³ (maksimum 2× acuan); `tau_lat_h` = latensi (jam); `mask` = porsi penurunan SpO2 yang disembunyikan oleh COHb pada oksimeter.

| Skenario | eff_spo2 (poin) | eff_hr (bpm) | tau_lat_h | mask |
|---|---|---|---|---|
| `tanpa_respons` | 0 – 0 | 0 – 0 | 1 – 6 | 0 |
| `literatur_sehat` | 0 – 1 | 0 – 4 | 1 – 6 | 0 |
| `rentan_optimis` | 1 – 3 | 3 – 10 | 0.5 – 3 | 0 |
| `co_masking` | 1 – 3 | 0 – 4 | 1 – 6 | 1 |

## Pilihan desain kontroler (bukan data)

| Konfigurasi | Nilai |
|---|---|
| Batas naik ISPU (LOW / MEDIUM / TURBO) | (15.5, 55.4, 150.4) µg/m³ |
| Lantai ambang absolut | (10.0, 25.0, 60.0) µg/m³ |
| Hysteresis (ambang turun = × ambang naik) | 0.8 |
| Tahan sebelum turun | 15 menit |
| Penghalus PM2.5 (EMA) | 5.0 menit |
| Pengali profil rentan / flag biometrik | 0.6 / 0.7 |
| Fraksi kecepatan kipas (OFF/LOW/MED/TURBO) | (0.0, 0.3, 0.6, 1.0) |
| Koreksi firmware: kappa / bias asap | 0.15 / 1.5 |
| Batas RH pada rumus higroskopis | 90 % |
