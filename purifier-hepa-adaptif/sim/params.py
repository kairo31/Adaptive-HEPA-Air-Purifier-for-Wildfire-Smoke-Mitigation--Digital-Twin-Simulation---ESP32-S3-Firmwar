"""
params.py -- Tabel Asumsi Simulator dalam bentuk kode.

Sumber: Riset_Asap_Biometrik_2026-11-20.pdf (nomor [..] = nomor referensi di dokumen itu),
dengan koreksi hasil review (HR baseline bangun BUKAN dari [1]; rentang asma dilebarkan;
keyakinan [30] diturunkan).

Setiap parameter Monte Carlo = (lo, hi, distribusi) + sumber + keyakinan.
  dist "uni" = seragam di [lo, hi]; "log" = log-seragam (cocok untuk besaran yang rentangnya
  lebih dari satu orde, mis. ACH, laju deposisi, puncak PM2.5).
Rentang sengaja LEBAR (sesuai saran dokumen: uji dengan rentang lebar bila keyakinan rendah).
Ubah angka di sini, bukan di simulator.py.

Baris tabel yang TIDAK dipakai model ini (hanya konteks): risiko IGD asma/PPOK, penurunan
FEV1/FVC lansia, occult hypoxemia. Itu keluaran klinis jam-hari, bukan sinyal menit-level.
"""
from collections import namedtuple
import numpy as np

Param = namedtuple("Param", "lo hi dist unit src conf note")


def draw(p, n, rng):
    """Ambil n sampel dari parameter p."""
    if p.dist == "log":
        return np.exp(rng.uniform(np.log(p.lo), np.log(p.hi), n))
    return rng.uniform(p.lo, p.hi, n)


PARAMS = {
    # ---------------- B. Dinamika PM2.5 dalam ruangan ----------------
    "ach_open":   Param(1.0, 5.0, "log", "1/jam", "[27][28][29]", "sedang",
                        "ACH rumah tropis berventilasi (rerata Rumoh Aceh 4,06)"),
    "ach_closed": Param(0.2, 2.0, "log", "1/jam", "[10][11]", "tinggi",
                        "ACH rumah tertutup/AC (studi empat musim)"),
    "pen":        Param(0.6, 1.0, "uni", "-", "AP", "rendah", "faktor penetrasi P"),
    "dep":        Param(0.05, 1.0, "log", "1/jam", "[11]", "sedang-tinggi", "laju deposisi k"),
    "src":        Param(5.0, 100.0, "log", "ug/m3/jam", "AP", "rendah",
                        "sumber dalam ruang S/V; hanya aktif pada 30% run (tipikal ~0)"),
    "vol":        Param(30.0, 45.0, "uni", "m3", "AP", "rendah", "volume kamar"),
    "cadr_rated": Param(100.0, 400.0, "uni", "m3/jam", "[39][40]", "tinggi", "smoke CADR label"),
    "cadr_eff":   Param(0.33, 1.0, "uni", "-", "[42]", "sedang",
                        "CADR efektif / CADR lab (mixing, pintu terbuka)"),

    # ---------------- Episode asap luar ruangan ----------------
    "pm_base":    Param(5.0, 20.0, "uni", "ug/m3", "AP", "rendah", "PM2.5 latar sebelum episode"),
    "pm_peak":    Param(50.0, 500.0, "log", "ug/m3", "[13][35]", "sedang",
                        "puncak plateau episode (tabel: 35-700+; dipersempit utk stabilitas)"),
    "ep_start_d": Param(1.0, 1.5, "uni", "hari", "desain", "-", "episode mulai (hari ke-0 = kalibrasi baseline)"),
    "ep_dur_d":   Param(3.0, 5.0, "uni", "hari", "AP", "rendah",
                        "durasi plateau (tabel: 3-7, rentang 1-14; dipersempit agar muat jendela 8 hari)"),
    "ep_rampup_d": Param(0.3, 1.0, "uni", "hari", "AP", "rendah", "waktu naik"),
    "ep_rampdn_d": Param(0.5, 1.5, "uni", "hari", "AP", "rendah", "waktu turun"),

    # ---------------- C. Sensor PMS5003 ----------------
    "rh_mean":    Param(70.0, 90.0, "uni", "%RH", "AP+[19]", "rendah-sedang", "RH rerata tropis"),
    "kappa":      Param(0.05, 0.20, "uni", "-", "AP+[17][18]", "sedang",
                        "kappa higroskopis aerosol SEBENARNYA (firmware menganggap 0,15). Rentang dipilih agar "
                        "bias tanpa koreksi pada RH 75-90% ~ +30..+110%, konsisten dgn [16] (hingga +90%)"),
    "smoke_bias": Param(1.2, 2.0, "uni", "x", "[16]", "sedang-tinggi",
                        "PMS5003 membaca berlebih saat asap; dikalikan efek RH (dianggap independen -> "
                        "galat gabungan tanpa koreksi mungkin berlebihan)"),

    # ---------------- D. MAX30102 / PPG ----------------
    "spo2_bias":  Param(0.3, 1.3, "uni", "poin", "[23][24][25]", "tinggi", "bias positif (pigmentasi sedang-gelap)"),
    "spo2_sigma": Param(1.0, 3.0, "uni", "poin", "[20][21][23]+AP", "rendah-sedang",
                        "simpangan baku galat SpO2 per sampel (Arms 3-4% dari bias + ini)"),
    "bio_dropout": Param(0.05, 0.20, "uni", "-", "AP+[20]", "rendah", "porsi sampel dibuang (SQI buruk)"),

    # ---------------- E. Baseline tidur ----------------
    "hr_sleep_dip": Param(0.05, 0.20, "uni", "-", "[31][32]+AP", "sedang(arah)/rendah(besaran)",
                          "penurunan HR NREM relatif terhadap HR bangun"),
}

# Rumus pertumbuhan higroskopis meledak mendekati RH 100%; RH efektif dibatasi di sini. (Temuan verifikasi V3)
RH_CAP = 90.0

# --- Fisiologi tetap (nilai tipikal; variasi antar-individu ada di simulator.py) ---
#   SpO2 bangun ~ N(97.5, 0.8) klip [95.5, 99]   [1]  tinggi
#   offset SpO2 tidur -1.5 poin (rerata semalam ~96)  [30] RENDAH-sedang (diturunkan dari 'tinggi')
#   HR bangun ~ N(75, 8) klip [60, 100]   -- AP; angka 86 bpm di [1] diukur SAAT terpapar, bukan baseline
#   HR REM: simpangan 6 bpm vs 3 bpm   [31][32]+AP
#   dip SpO2: REM 3/jam, NREM 0,5/jam, amplitudo 1-3 poin, durasi 3 menit   AP (sumber konsumen)

# --- Skenario respons biometrik ---
#   eff_spo2 / eff_hr = besar respons pada paparan acuan 150 ug/m3 (maks 2x acuan).
#   tau_lat_h = latensi respons (konstanta waktu EMA paparan), jam.   [2][9]: 1-24 jam
#   mask = porsi penurunan SpO2 sebenarnya yang DISEMBUNYIKAN oksimeter oleh COHb. [6][7][8]
SCENARIOS = {
    "tanpa_respons":   dict(eff_spo2=(0.0, 0.0), eff_hr=(0.0, 0.0), tau_lat_h=(1.0, 6.0), mask=0.0),
    "literatur_sehat": dict(eff_spo2=(0.0, 1.0), eff_hr=(0.0, 4.0), tau_lat_h=(1.0, 6.0), mask=0.0),
    # kasus TERBAIK untuk biometrik (asumsi pribadi; tidak ada bukti dip SpO2 menit-level):
    "rentan_optimis":  dict(eff_spo2=(1.0, 3.0), eff_hr=(3.0, 10.0), tau_lat_h=(0.5, 3.0), mask=0.0),
    # SpO2 sebenarnya turun tetapi oksimeter tidak melihatnya:
    "co_masking":      dict(eff_spo2=(1.0, 3.0), eff_hr=(0.0, 4.0), tau_lat_h=(1.0, 6.0), mask=1.0),
}

# --- Konfigurasi kontroler & simulasi (pilihan desain, bukan data) ---
CFG = dict(
    ispu_up=(15.5, 55.4, 150.4),   # batas atas ISPU Baik/Sedang/Tidak Sehat -> naik ke LOW/MEDIUM/TURBO
    thr_floor=(10.0, 25.0, 60.0),   # LANTAI ambang naik (ug/m3) setelah dikali pengali: tanpa ini ambang ketat
                                    # jatuh di bawah latar udara bersih+noise sensor -> kipas berkedip (temuan demo)  AP
    hyst=0.8,                       # ambang turun = 0,8 x ambang naik
    hold_down_min=15,               # tahan minimal 15 menit sebelum TURUN level (naik langsung)
    ema_pm_min=5.0,                 # konstanta waktu penghalus PM2.5 (menit)
    speed=(0.0, 0.3, 0.6, 1.0),     # fraksi kecepatan kipas; CADR ~ kecepatan, daya ~ kecepatan^3
    f_vuln=0.6,                     # pengali ambang untuk profil rentan (kontroler B, C, D)   AP
    f_bio=0.7,                      # pengali TAMBAHAN saat flag aktif (C); D = flag SELALU aktif  AP
    ref_pm=150.0,                   # paparan acuan untuk besar respons fisiologis
    true_stress=(2.0, 8.0),         # "stres fisiologis sebenarnya": dSpO2 >= 2 poin ATAU dHR >= 8 bpm
    bio=dict(
        period_min=3,               # duty-cycle: satu pengukuran tiap 3 menit
        thr_spo2=3.0,               # turun >= 3 poin dari baseline pribadi (EMA terhaluskan)
        thr_hr=10.0,                # naik >= 10 bpm dari baseline pribadi saat diam
        ema_alpha=0.3,              # penghalus deviasi (per sampel valid, ~10 menit)
        baseline_alpha=0.02,        # laju belajar baseline (per sampel valid)
        baseline_pm_max=25.0,       # baseline hanya diperbarui bila PM2.5 <= ini
        gate_pm=15.5,               # flag hanya boleh aktif bila PM2.5 > ini
        timeout_min=20,             # tanpa data valid > 20 menit -> kembali ke mode PM saja
    ),
    firmware=dict(kappa_est=0.15, smoke_est=1.5),   # koreksi RH & asap yang ditanam di firmware
)


def print_param_table():
    """Cetak tabel asumsi yang dipakai (untuk lampiran laporan)."""
    print(f"{'parameter':14s} {'rentang':>16s} {'dist':>5s} {'satuan':>10s}  {'sumber':16s} keyakinan")
    for k, p in PARAMS.items():
        print(f"{k:14s} {p.lo:>7g}-{p.hi:<8g} {p.dist:>5s} {p.unit:>10s}  {p.src:16s} {p.conf}")
    print("\nSkenario respons biometrik:")
    for k, s in SCENARIOS.items():
        print(f"  {k:16s} {s}")
