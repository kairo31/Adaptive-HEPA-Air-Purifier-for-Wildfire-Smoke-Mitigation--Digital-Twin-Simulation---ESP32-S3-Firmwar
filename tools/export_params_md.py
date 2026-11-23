#!/usr/bin/env python3
"""Ekspor tabel asumsi (sim/params.py) ke docs/asumsi.md."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))

from params import PARAMS, SCENARIOS, CFG, RH_CAP  # noqa: E402

lines = [
    "# Tabel asumsi simulator",
    "",
    "Dibangkitkan otomatis dari `sim/params.py` oleh `tools/export_params_md.py`. **Ubah angka di `params.py`, bukan di file ini.**",
    "",
    "Nomor sumber `[n]` merujuk ke [referensi.md](referensi.md). `AP` = asumsi pribadi (belum ada sumber langsung, diuji dengan rentang lebar).",
    "",
    "## Parameter Monte Carlo",
    "",
    "| Parameter | Rentang | Distribusi | Satuan | Sumber | Keyakinan | Catatan |",
    "|---|---|---|---|---|---|---|",
]
for k, p in PARAMS.items():
    dist = "log-seragam" if p.dist == "log" else "seragam"
    lines.append(f"| `{k}` | {p.lo:g} – {p.hi:g} | {dist} | {p.unit} | {p.src} | {p.conf} | {p.note} |")
lines += [
    "",
    "## Skenario respons biometrik",
    "",
    "`eff_spo2` / `eff_hr` = besar respons pada paparan acuan 150 µg/m³ (maksimum 2× acuan); `tau_lat_h` = latensi (jam); "
    "`mask` = porsi penurunan SpO2 yang disembunyikan oleh COHb pada oksimeter.",
    "",
    "| Skenario | eff_spo2 (poin) | eff_hr (bpm) | tau_lat_h | mask |",
    "|---|---|---|---|---|",
]
for k, s in SCENARIOS.items():
    lines.append(f"| `{k}` | {s['eff_spo2'][0]:g} – {s['eff_spo2'][1]:g} | {s['eff_hr'][0]:g} – {s['eff_hr'][1]:g} | "
                 f"{s['tau_lat_h'][0]:g} – {s['tau_lat_h'][1]:g} | {s['mask']:g} |")
lines += [
    "",
    "## Pilihan desain kontroler (bukan data)",
    "",
    "| Konfigurasi | Nilai |",
    "|---|---|",
    f"| Batas naik ISPU (LOW / MEDIUM / TURBO) | {CFG['ispu_up']} µg/m³ |",
    f"| Lantai ambang absolut | {CFG['thr_floor']} µg/m³ |",
    f"| Hysteresis (ambang turun = × ambang naik) | {CFG['hyst']} |",
    f"| Tahan sebelum turun | {CFG['hold_down_min']} menit |",
    f"| Penghalus PM2.5 (EMA) | {CFG['ema_pm_min']} menit |",
    f"| Pengali profil rentan / flag biometrik | {CFG['f_vuln']} / {CFG['f_bio']} |",
    f"| Fraksi kecepatan kipas (OFF/LOW/MED/TURBO) | {CFG['speed']} |",
    f"| Koreksi firmware: kappa / bias asap | {CFG['firmware']['kappa_est']} / {CFG['firmware']['smoke_est']} |",
    f"| Batas RH pada rumus higroskopis | {RH_CAP:g} % |",
    "",
]
(ROOT / "docs" / "asumsi.md").write_text("\n".join(lines), encoding="utf-8")
print("docs/asumsi.md ditulis")
