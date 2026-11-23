# Hasil simulasi

Pertanyaan yang diuji: **apakah menambahkan biometrik (SpO2/HR dari klip jari) ke kendali kipas memberi manfaat dibanding kendali berbasis PM2.5 saja?**

Semua angka di bawah berasal dari kode di repo ini dengan asumsi bawaan ([asumsi.md](asumsi.md)), rumah berventilasi **terbuka** (ACH ±1–5 /jam), jendela 8 hari, episode asap sintetis. Monte Carlo: **300 run** per kombinasi (`make mc`, seed 1). Sapuan: **150 run** per titik (`make sweep`, seed 2). Dokumen riset menyarankan ≥1.000 run: ulangi dengan `python sim/simulator.py mc --n 1000` sebelum mengutip angka.

## Empat kontroler

| Kode | Kontroler | Fungsi |
|---|---|---|
| A | PM2.5 saja | Ambang ISPU pada rata-rata pendek, hysteresis, tahan 15 menit sebelum turun |
| B | A + profil statis | Ambang ×0,6 untuk pengguna rentan (asma, PPOK, lansia) |
| C | B + biometrik | Flag SpO2/HR menurunkan ambang ×0,7. **C−B = nilai tambah biometrik murni** |
| D | Kontrol null | Seperti C tetapi "flag" selalu aktif. Menjawab: apakah C lebih baik daripada sekadar lebih waspada? |

Semua kontroler dijalankan pada "dunia" yang sama (angka acak bersama), sehingga perbandingannya berpasangan.

## 1. Profil statis memberi manfaat terbesar

Skenario `tanpa_respons` (tubuh tidak bereaksi terhadap asap):

| Grup | Kontrol | Paparan rerata (µg/m³) | Energi kipas (% TURBO terus-menerus) |
|---|---|---|---|
| sehat | A = B | 76,5 | 19,9 |
| sehat | C | 76,1 | 20,3 |
| sehat | D | 71,9 | 29,2 |
| rentan | A | 76,5 | 19,9 |
| rentan | B | 70,1 | 34,1 |
| rentan | C | 69,9 | 34,5 |
| rentan | D | 66,8 | 46,4 |

Menurunkan ambang untuk pengguna rentan (A→B) mengurangi paparan sekitar 6 µg/m³ (±8%) dengan tambahan energi. "Paparan" = rata-rata PM2.5 kamar selama pengguna berada di kamar pada hari-hari episode asap.

## 2. Biometrik menambah sangat sedikit

Selisih C−B pada paparan (µg/m³; negatif = C lebih baik) dan kualitas flag:

| Skenario | C−B sehat | C−B rentan | Onset flag palsu/hari | Youden J | Menit-flag palsu |
|---|---|---|---|---|---|
| `tanpa_respons` | −0,4 | −0,3 | 1,4–1,5 | tak terdefinisi (tidak ada stres nyata) | 100% |
| `literatur_sehat` | −0,5 | −0,3 | 1,7–1,8 | tak terdefinisi | 100% |
| `rentan_optimis` (kasus terbaik, asumsi pribadi) | −1,4 | −0,7 | 1,9–2,1 | +0,15 / +0,16 | 83–84% |
| `co_masking` (SpO2 tersembunyi CO) | −0,4 | −0,3 | 1,3–1,4 | −0,04 / −0,02 | 85–86% |

**Youden J** = sensitivitas − laju alarm palsu. J = 0 berarti flag tidak mengandung informasi, J = 1 sempurna. Pada skenario terbaik pun J hanya ±0,15.

## 3. Kapan biometrik mulai berguna (sapuan ukuran efek, grup rentan)

Gambar: [`images/fig_sweep.png`](images/fig_sweep.png). Data: [`../results/hasil_sweep.csv`](../results/hasil_sweep.csv).

- Di dalam rentang literatur orang sehat (ΔSpO2 ≤ 1 poin, ΔHR ≤ 4 bpm): **J antara −0,09 dan +0,07**, yaitu hampir tanpa informasi.
- Saat respons HR sebenarnya mencapai **10–15 bpm**: J naik ke **0,26–0,33** untuk ΔSpO2 ≤ 3 poin (0,18–0,22 pada ΔSpO2 = 5), yaitu sekitar 2,5–4× batas atas literatur.
- Respons SpO2 ≥ 2 poin saja (ΔHR = 0) memberi J 0,13–0,16.
- Manfaat paparan C−B di seluruh grid hanya **−0,2 sampai −1,9 µg/m³**, dengan 1,2–1,9 onset palsu per hari.

## 4. Jenis rumah menentukan lebih banyak daripada logika kontrol

`make housing` (150 run, `tanpa_respons`, grup sehat):

| Rumah | Kontrol A: paparan | Menit > 55,4 µg/m³ | Kontrol D: paparan | Menit > 55,4 µg/m³ |
|---|---|---|---|---|
| terbuka | 73,9 | 51% | 69,5 | 47% |
| tertutup | 44,2 | 25% | 40,6 | 21% |

Di rumah berventilasi terbuka (pergantian udara ±4 /jam), purifier berukuran umum hanya punya wewenang terbatas: menutup jendela dan pintu lebih berpengaruh daripada pengaturan kipas apa pun.

## Cara membaca hasil ini

- Ini **bukan bukti** bahwa biometrik tidak berguna. Artinya: dengan pengetahuan dan asumsi sekarang, tambahannya kecil. Besar kecilnya bergantung pada pilihan di [`sim/params.py`](../sim/params.py).
- **Asumsi pribadi yang berpengaruh:** ambang flag (3 poin SpO2 / 10 bpm HR), penghalus EMA, definisi "stres nyata" (ΔSpO2 ≥ 2 atau ΔHR ≥ 8), simpangan baku galat SpO2 (1–3 poin), pengali ambang (0,6 dan 0,7).
- Detektor yang lebih cerdas (misalnya tren HR berjam-jam atau fitur HRV saat tidur) **belum dicoba**.
- Resolusi 1 menit melewatkan dip SpO2 yang sangat singkat.
- Model sensor mengalikan efek RH dan bias asap secara independen, sehingga galat gabungan tanpa koreksi bisa berlebihan. Galat setelah koreksi (NRMSE per jam 0,27) berada di tepi atas kisaran literatur (0,16–0,27).
- Ini baru **verifikasi** (kode sesuai model), belum **validasi** terhadap data lapangan.

## Pelajaran dari proses pembuatan

Verifikasi menemukan beberapa cacat desain yang sudah diperbaiki di kode:

1. Rumus higroskopis meledak mendekati RH 100% → RH efektif dibatasi 90%.
2. Ambang ketat jatuh di bawah latar udara bersih → kipas berkedip; ditambah lantai ambang absolut (10/25/60 µg/m³).
3. Pengali profil dan flag awalnya digabung dengan `min`, sehingga C−B nol *secara konstruksi* untuk pengguna rentan → diganti perkalian.
4. Metrik *lift* tidak monoton karena dibatasi 1/prevalensi stres → diganti Youden J.
