# Ringkasan riset fondasi

Ringkasan temuan yang mendasari asumsi simulator, **beserta catatan kehati-hatian** yang ditemukan saat meninjau dokumen riset awal. Nomor `[n]` merujuk ke [referensi.md](referensi.md). Angka diambil dari dokumen riset awal kecuali dinyatakan lain.

## Kesimpulan desain

Untuk orang sehat pada paparan asap dalam ruangan yang realistis, **SpO2 praktis tidak berubah** dan perubahan detak jantung (HR) serta variabilitasnya (HRV) kecil dan tidak konsisten. Pada kelompok rentan, eksaserbasi muncul dalam **jam sampai hari**, bukan sebagai penurunan SpO2 menit-per-menit yang bisa dialarm. Karena itu kendali kipas sebaiknya bertumpu pada **PM2.5**, dan biometrik diperlakukan sebagai tambahan opsional, bukan pemicu utama.

## Temuan utama

| Topik | Temuan | Sumber |
|---|---|---|
| SpO2 saat kabut asap | Rerata 97,81% (SD 1,36), normal, meski 72,6% subjek menunjukkan penurunan fungsi paru | [1] |
| HRV, paparan terkontrol | Efek gabungan tidak signifikan (SMD −0,019); ≤3 jam hampir nol (−0,026); protokol lebih panjang −0,221 | [2] |
| HRV, PM2.5 ambient | Per +10 µg/m³: SDNN −0,92%, rMSSD −1,47%, HF −2,17% | [3] |
| Konsentrasi ekstrem | n=10, 250 µg/m³, 2 jam: HR +3,8 bpm (CI 0,3–7,4) | [4] |
| Latensi | Efek HRV dalam 1–24 jam; dampak klinis rentan lag 0–5+ hari | [2][9][45][46][47] |
| Jebakan CO | Oksimeter tidak membedakan COHb dari oksihemoglobin: SpO2 terbaca terlalu tinggi kira-kira sebesar kadar COHb | [6][7][8] |
| Rumah terbuka vs tertutup | ACH tertutup 0,3–1,4 /jam; rumah tropis berventilasi ±4 /jam | [11][27] |
| Efek purifier | PM2.5 dalam ruangan turun 48–78%; CADR efektif seluruh rumah bisa ±1/3 CADR lab | [11][42] |
| Sensor PMS5003 | Membaca >1,5× saat asap; bias hingga +90% pada RH >75%; NRMSE <27% setelah koreksi | [16] |
| MAX30102 | Bias fingertip +1,84% (SD 1,32); pergelangan jauh kurang andal | [20] |
| Bias warna kulit | Overestimasi +0,3 s.d. +1,3%; Arms 3,96–4,71% | [23][24][25] |
| Ambang | ISPU PM2.5 24 jam: 15,5 / 55,4 / 150,4 / 250,4 µg/m³; WHO 24 jam: 15 | [33][34][35] |

## Catatan kehati-hatian (hasil tinjauan)

1. **Studi Riau [1] tidak menunjukkan "SpO2 tidak berubah".** Studi ini potong-lintang satu waktu, tanpa kelompok kontrol dan tanpa ukuran sebelum paparan. Yang bisa disimpulkan: SpO2 *normal* saat paparan sangat berat. HR 86 ± 14,6 bpm diukur *saat* terpapar, jadi bukan baseline. COHb 5,74% adalah *prediksi dari CO napas*, bukan hasil tes darah.
2. **Penyamaran CO.** Memakai kedua rumus di [7] dan [8] pada COHb 5,74% memberi saturasi sebenarnya sekitar **91–94%**, bukan satu angka tunggal. Pakai rentang.
3. **Rentang risiko asma terlalu sempit di dokumen awal.** Tabel menulis +1 s.d. +4,4% per 10 µg/m³, padahal [45] dan [47] melaporkan OR 1,11–1,13 (±+11–13%). Pakai ±2–13% dan catat bahwa definisi hasilnya berbeda antar studi.
4. **Keyakinan [30] tidak konsisten** (teks: rendah, tabel: tinggi). Diturunkan. Idealnya diganti data normatif oksimetri semalam dari jurnal tidur.
5. **Satuan studi chamber [9]** ditulis 35–500 *mg*/m³, yang terdengar terlalu tinggi untuk PM2.5 asap kayu. **Belum bisa diverifikasi** (halaman diblokir). Jika sebenarnya µg/m³, kesimpulan "tidak bisa diekstrapolasi ke level dalam ruangan" menjadi jauh lebih lemah.
6. **ISPU adalah rata-rata 24 jam**, sedangkan kipas harus bereaksi dalam menit. Simulator dan firmware memakai ambang ISPU pada rata-rata bergulir pendek (EMA 5 menit); rata-rata 24 jam hanya cocok untuk pelaporan kepatuhan.
7. **Sumber lain belum diverifikasi ulang.** Lihat catatan status di [referensi.md](referensi.md).
