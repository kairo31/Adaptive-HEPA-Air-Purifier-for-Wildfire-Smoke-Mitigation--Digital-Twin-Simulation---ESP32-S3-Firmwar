"""
simulator.py -- Simulasi purifier HEPA adaptif-biometrik (digital twin, tanpa perangkat keras).

Empat kontroler dibandingkan pada "dunia" yang SAMA (angka acak bersama -> perbandingan berpasangan):
  A  PM2.5 saja (ambang ISPU pada rata-rata pendek)
  B  A + profil kerentanan statis (ambang lebih rendah untuk pengguna rentan)
  C  B + biometrik langsung (flag SpO2/HR menurunkan ambang)     -> C-B = nilai tambah biometrik
  D  A dengan ambang SELALU ketat (kontrol null)                  -> C vs D: apakah C lebih baik
                                                                     daripada sekadar "lebih waspada"?

Satu langkah = 1 menit. Semua array berbentuk (waktu, run) agar setiap langkah vektor-per-run.

Cara pakai:
    python simulator.py verify          # uji verifikasi (jalankan PERTAMA)
    python simulator.py demo            # satu run + grafik rinci
    python simulator.py mc --n 300      # Monte Carlo semua skenario x grup
    python simulator.py sweep           # sapu ukuran efek biometrik (peta panas)
    python simulator.py params          # cetak tabel asumsi yang dipakai
Opsi: --n, --seed, --housing terbuka|tertutup, --days, --out, --outdoor data.csv

PERINGATAN: ini simulasi dengan asumsi. Hubungan PM2.5 -> SpO2/HR di sini adalah ASUMSI skenario,
bukan fakta terbukti; simulator menguji LOGIKA kontrol, bukan klaim kesehatan. Bukan alat medis.
"""
import argparse
import copy
import csv
import os
import time

import numpy as np

from params import PARAMS, SCENARIOS, CFG, RH_CAP, draw, print_param_table

LEVELS = ("OFF", "LOW", "MEDIUM", "TURBO")
CTRLS = ("A", "B", "C", "D")


# ===================================================================== utilitas
def smoothstep(x):
    return x * x * (3 - 2 * x)


def ar1(rng, T, n, phi, sigma=1.0):
    """Proses AR(1) stasioner, simpangan baku sigma. Bentuk (T, n)."""
    e = rng.standard_normal((T, n)) * (sigma * np.sqrt(1 - phi ** 2))
    x = np.empty((T, n))
    x[0] = rng.standard_normal(n) * sigma
    for i in range(1, T):
        x[i] = phi * x[i - 1] + e[i]
    return x


def load_outdoor_csv(path, T):
    """Satu kolom PM2.5 per JAM (mis. dari OpenAQ/ISPU) -> deret per menit sepanjang T menit."""
    x = np.loadtxt(path, delimiter=",", ndmin=1)
    if x.ndim > 1:
        x = x[:, -1]
    if len(x) < T / 60.0:
        print(f"  [peringatan] data luar hanya {len(x)} jam < {T/60:.0f} jam; nilai terakhir diperpanjang")
    return np.interp(np.arange(T) / 60.0, np.arange(len(x)), x)


# ===================================================================== dunia (eksogen)
def make_world(n, rng, scen, group, housing, T_days, cfg, outdoor=None):
    """Bangkitkan semua deret yang TIDAK bergantung pada keputusan kontroler."""
    T = int(T_days * 1440)
    t = np.arange(T)
    tt = t[:, None]
    hour = (t / 60.0) % 24
    d = lambda name: draw(PARAMS[name], n, rng)
    W = {"n": n, "T": T}

    # ---- PM2.5 luar: episode asap sintetis (atau data nyata)
    base, peak = d("pm_base"), d("pm_peak")
    if outdoor is not None:
        W["cout"] = np.repeat(outdoor[:T, None], n, axis=1).astype(float)
    else:
        start, dur, rup, rdn = d("ep_start_d"), d("ep_dur_d"), d("ep_rampup_d"), d("ep_rampdn_d")
        td = (t / 1440.0)[:, None]
        env = smoothstep(np.clip((td - start) / rup, 0, 1)) * smoothstep(np.clip((start + dur - td) / rdn, 0, 1))
        diurnal = 1 + 0.3 * np.cos(2 * np.pi * (hour[:, None] - 5) / 24)      # malam-pagi lebih pekat
        plume = np.exp(ar1(rng, T, n, 0.995, 0.3) - 0.045)                     # fluktuasi berjam-jam
        W["cout"] = np.clip(base + env * peak * diurnal * plume, 2, 1500)

    # ---- parameter ruangan & purifier
    a = d("ach_open") if housing == "terbuka" else d("ach_closed")
    W.update(a=a, P=d("pen"), k=d("dep"), V=d("vol"))
    W["S"] = np.where(rng.random(n) < 0.7, 0.0, d("src"))
    cadr = d("cadr_rated") * d("cadr_eff")                                    # m3/jam efektif @ TURBO
    speed = np.array(cfg["speed"])
    W["lam_lv"] = speed[None, :] * cadr[:, None] / W["V"][:, None]            # (n,4) laju removal 1/jam
    W["cin0"] = W["cout"][0] * a * W["P"] / (a + W["k"])                      # keadaan awal tanpa purifier

    # ---- RH & sensor PM
    W["rh"] = np.clip(d("rh_mean") + 10 * np.cos(2 * np.pi * (hour[:, None] - 5) / 24) + ar1(rng, T, n, 0.99, 3), 40, 99)
    W["kappa"], W["s_bias"] = d("kappa"), d("smoke_bias")
    W["gain"] = 1 + rng.normal(0, 0.08, n)
    W["pm_noise"] = rng.standard_normal((T, n))
    W["pm_drop"] = rng.random((T, n)) < 0.002

    # ---- jadwal tidur & kehadiran di kamar (22:00-06:00 tidur; di kamar 21:00-07:00)
    night_idx = np.floor((t - 720) / 1440).astype(int) + 1
    nights = int(night_idx.max()) + 1
    kk = np.arange(nights)[:, None]
    onset = (kk - 1) * 1440 + 1320 + rng.normal(0, 30, (nights, n))
    wake = (kk - 1) * 1440 + 1800 + rng.normal(0, 30, (nights, n))
    on_t, wk_t = onset[night_idx], wake[night_idx]
    sleeping = (tt >= on_t) & (tt < wk_t)
    occupied = (tt >= on_t - 60) & (tt < wk_t + 60)
    mso = tt - on_t                                                            # menit sejak mulai tidur
    rem_len = np.minimum(10 + 5 * (np.maximum(mso, 0) // 90), 25)
    rem = sleeping & (mso >= 90) & ((mso % 90) >= 90 - rem_len)               # fase REM di akhir tiap siklus 90 mnt
    W.update(sleeping=sleeping, occupied=occupied, rem=rem)

    # ---- aktivitas (jalan) dalam blok 10 menit
    nb = T // 10 + 2
    blk = t // 10
    u, amp = rng.random((nb, n)), rng.uniform(15, 40, (nb, n))
    walk = occupied & (u[blk] < np.where(sleeping, 0.03, 0.15))
    walk_hr = np.where(walk, amp[blk], 0.0)
    W["still"] = ~walk | (rng.random((T, n)) < 0.05)                           # akselerometer salah 5%

    # ---- fisiologi dasar (tanpa asap)
    sp_awake = np.clip(rng.normal(97.5, 0.8, n), 95.5, 99.0)
    hr_awake = np.clip(rng.normal(75, 8, n), 60, 100)
    dip_nrem = d("hr_sleep_dip")
    rate = np.where(rem, 3.0, np.where(sleeping, 0.5, 0.0)) / 60.0             # dip SpO2 per menit
    starts = (rng.random((T, n)) < rate) * rng.uniform(1, 3, (T, n))
    dips = starts.copy()
    for s in (1, 2):                                                           # tiap dip bertahan 3 menit
        dips[s:] = np.maximum(dips[s:], starts[:-s])
    W["spo2_base"] = sp_awake - 1.5 * sleeping - dips + ar1(rng, T, n, 0.9, 0.5)
    hr_level = hr_awake * (1 - dip_nrem * (sleeping & ~rem) - 0.5 * dip_nrem * rem)
    W["hr_base"] = hr_level + np.where(rem, 6.0, 3.0) * ar1(rng, T, n, 0.9, 1.0) + walk_hr

    # ---- wearable: jadwal duty-cycle, validitas (SQI), galat ukur
    period = cfg["bio"]["period_min"]
    phase = rng.integers(0, period, n)
    sched = ((tt + phase) % period) == 0
    worn = (rng.random((nights, n)) < 0.9)[night_idx]
    conn = rng.random((T, n)) < 0.98
    motion_bad = walk & (rng.random((T, n)) < 0.5)
    W["bio_valid"] = occupied & worn & conn & sched & ~motion_bad & (rng.random((T, n)) >= d("bio_dropout"))
    sg, bias = d("spo2_sigma"), d("spo2_bias")
    outl = rng.random((T, n)) < 0.01
    W["spo2_err"] = bias + sg * (0.7 * rng.standard_normal((T, n)) + 0.7 * ar1(rng, T, n, 0.98, 1.0)) \
        - outl * rng.uniform(0, 8, (T, n))
    W["hr_err"] = 2.0 * rng.standard_normal((T, n)) + (rng.random((T, n)) < 0.01) * rng.uniform(-25, 25, (T, n))

    # ---- skenario respons fisiologis terhadap paparan
    W["eff_sp"] = rng.uniform(*scen["eff_spo2"], n)
    W["eff_hr"] = rng.uniform(*scen["eff_hr"], n)
    tau = rng.uniform(*scen["tau_lat_h"], n)
    W["a_lat"] = 1 - np.exp(-1.0 / (tau * 60))
    W["mask"] = scen["mask"]
    W["vuln"] = np.full(n, group == "rentan")
    return W


# ===================================================================== model fisik & sensor
def room_step(cin, cout, a, P, k, S, lam, dt_h=1 / 60):
    """Keseimbangan massa satu zona, solusi eksak per langkah:
       dC/dt = a*P*Cout - (a + k + lam)*C + S/V."""
    L = a + k + lam
    ss = (a * P * cout + S) / L
    return ss + (cin - ss) * np.exp(-L * dt_h)


def sensor_raw(cin, rh, kappa, s_bias, gain, noise, drop, last):
    """PMS5003 virtual: pertumbuhan higroskopis (kappa), bias asap, galat gain, noise, dropout."""
    growth = 1 + (kappa / 1.65) / (100 / np.minimum(rh, RH_CAP) - 1)
    smoke = 1 + (s_bias - 1) * np.clip(cin / 50.0, 0, 1)
    true_read = cin * growth * smoke * gain
    meas = np.maximum(true_read + (0.08 * true_read + 2.0) * noise, 0)
    return np.round(np.where(drop, last, meas))


def firmware_correct(raw, rh, kappa_est, smoke_est):
    """Koreksi RH (higroskopis) lalu koreksi asap -- ini yang akan ditanam di firmware."""
    x = raw / (1 + (kappa_est / 1.65) / (100 / np.minimum(rh, RH_CAP) - 1))
    return x / (1 + (smoke_est - 1) * np.clip(x / 50.0, 0, 1))


# ===================================================================== kontroler
def decide(pm_f, f, level, since, cfg):
    """State machine 4 level. NAIK langsung; TURUN hanya bila di bawah ambang-turun (hysteresis)
    DAN sudah >= hold_down_min menit sejak perubahan terakhir. f = pengali ambang (<1 = lebih waspada)."""
    up = np.maximum(np.array(cfg["ispu_up"])[None, :] * f[:, None], np.array(cfg["thr_floor"])[None, :])
    t_up = (pm_f[:, None] > up).sum(1)
    t_dn = (pm_f[:, None] > up * cfg["hyst"]).sum(1)
    new = np.where(t_up > level, t_up, np.where((t_dn < level) & (since >= cfg["hold_down_min"]), t_dn, level))
    since = np.where(new != level, 0.0, since + 1.0)
    return new, since


def _init_state(W, c):
    n = W["n"]
    s = dict(cin=W["cin0"].copy(), pm_last=W["cin0"].copy(), pm_f=W["cin0"].copy(),
             level=np.zeros(n, int), since=np.full(n, 999.0),
             sum_exp=np.zeros(n), c15=np.zeros(n), c55=np.zeros(n),
             lvmin=np.zeros((n, 4)), sw=np.zeros(n))
    if c == "C":
        s.update(E=W["cin0"].copy(), base_sp=np.full((2, n), np.nan), base_hr=np.full((2, n), np.nan),
                 e_sp=np.zeros(n), e_hr=np.zeros(n), flag=np.zeros(n, bool), since_valid=np.full(n, 999.0),
                 fl_min=np.zeros(n), st_min=np.zeros(n), tp_min=np.zeros(n), fp_min=np.zeros(n),
                 on_tot=np.zeros(n), on_false=np.zeros(n), have_min=np.zeros(n))
    return s


def run_world(W, cfg, controllers=CTRLS, trace_n=0, force_bio_off=False):
    """Loop tertutup. Mengembalikan metrik per run per kontroler (+ jejak waktu untuk trace_n run)."""
    T, n = W["T"], W["n"]
    ar = np.arange(n)
    bc, fw = cfg["bio"], cfg["firmware"]
    st = {c: _init_state(W, c) for c in controllers}
    alpha_pm = 1 - np.exp(-1.0 / cfg["ema_pm_min"])
    speed = np.array(cfg["speed"])
    f_prof = np.where(W["vuln"], cfg["f_vuln"], 1.0)
    ones = np.ones(n)
    ts_sp, ts_hr = cfg["true_stress"]
    epi_min = occ_epi_min = 0.0
    epi = W["cout"] > 35.0                                      # menit "episode asap" (eksogen)
    tr = None
    if trace_n:
        tr = {"cout": np.zeros((T, trace_n)), "sp": np.full((T, trace_n), np.nan), "hr": np.full((T, trace_n), np.nan),
              "flag": np.zeros((T, trace_n), bool), "stress": np.zeros((T, trace_n), bool)}
        tr["occ"], tr["sleep"] = W["occupied"][:, :trace_n].copy(), W["sleeping"][:, :trace_n].copy()
        for c in controllers:
            tr[c] = {k: np.zeros((T, trace_n)) for k in ("cin", "level", "pm_f")}

    for t in range(T):
        cout, rh, occ = W["cout"][t], W["rh"][t], W["occupied"][t]
        epi_t, epi_occ = epi[t], epi[t] & occ
        epi_min = epi_min + epi_t
        occ_epi_min = occ_epi_min + epi_occ
        for c in controllers:
            s = st[c]
            used = s["level"]
            s["cin"] = room_step(s["cin"], cout, W["a"], W["P"], W["k"], W["S"], W["lam_lv"][ar, used])
            raw = sensor_raw(s["cin"], rh, W["kappa"], W["s_bias"], W["gain"], W["pm_noise"][t], W["pm_drop"][t], s["pm_last"])
            s["pm_last"] = raw
            s["pm_f"] = s["pm_f"] + alpha_pm * (firmware_correct(raw, rh, fw["kappa_est"], fw["smoke_est"]) - s["pm_f"])

            if c == "A":
                f = ones
            elif c == "B":
                f = f_prof
            elif c == "D":                                         # kontrol null: "flag" selalu aktif
                f = f_prof * cfg["f_bio"]
            else:                                                  # ---- C: biometrik langsung
                x = np.where(occ, s["cin"], 0.8 * cout)            # paparan yang dirasakan (di luar kamar ~ udara luar)
                s["E"] = s["E"] + W["a_lat"] * (x - s["E"])
                rel = np.minimum(s["E"] / cfg["ref_pm"], 2.0)
                dsp_true, dhr_true = W["eff_sp"] * rel, W["eff_hr"] * rel
                valid = W["bio_valid"][t] & W["still"][t] & (not force_bio_off)
                sl = W["sleeping"][t].astype(int)
                sp = np.minimum(np.round(W["spo2_base"][t] - dsp_true * (1 - W["mask"]) + W["spo2_err"][t]), 100)
                hr = np.round(W["hr_base"][t] + dhr_true + W["hr_err"][t])
                cur_sp, cur_hr = s["base_sp"][sl, ar], s["base_hr"][sl, ar]
                upd = valid & (s["pm_f"] <= bc["baseline_pm_max"])           # baseline: hanya di udara bersih
                ab = bc["baseline_alpha"]
                s["base_sp"][sl[upd], ar[upd]] = np.where(np.isnan(cur_sp), sp, cur_sp + ab * (sp - cur_sp))[upd]
                s["base_hr"][sl[upd], ar[upd]] = np.where(np.isnan(cur_hr), hr, cur_hr + ab * (hr - cur_hr))[upd]
                have = valid & ~np.isnan(cur_sp) & ~np.isnan(cur_hr)
                ad = bc["ema_alpha"]
                s["e_sp"] = np.where(have, s["e_sp"] + ad * ((cur_sp - sp) - s["e_sp"]), s["e_sp"])
                s["e_hr"] = np.where(have, s["e_hr"] + ad * ((hr - cur_hr) - s["e_hr"]), s["e_hr"])
                s["since_valid"] = np.where(valid, 0.0, s["since_valid"] + 1.0)
                lost = s["since_valid"] > bc["timeout_min"]                  # fail-safe: kembali ke mode PM saja
                s["e_sp"] = np.where(lost, 0.0, s["e_sp"])
                s["e_hr"] = np.where(lost, 0.0, s["e_hr"])
                on = (s["e_sp"] >= bc["thr_spo2"]) | (s["e_hr"] >= bc["thr_hr"])
                off = (s["e_sp"] < 0.5 * bc["thr_spo2"]) & (s["e_hr"] < 0.5 * bc["thr_hr"])
                gate = s["pm_f"] > bc["gate_pm"]
                prev = s["flag"]
                s["flag"] = np.where(prev, gate & ~off, gate & on) & ~lost
                f = np.where(s["flag"], f_prof * cfg["f_bio"], f_prof)
                stress = (dsp_true >= ts_sp) | (dhr_true >= ts_hr)
                fo = s["flag"] & occ
                s["fl_min"] += fo
                s["st_min"] += stress & occ
                s["tp_min"] += fo & stress
                s["fp_min"] += fo & ~stress
                onset = s["flag"] & ~prev
                s["on_tot"] += onset
                s["on_false"] += onset & ~stress
                s["have_min"] += ~np.isnan(cur_sp) & ~np.isnan(cur_hr) & epi_occ

            new, s["since"] = decide(s["pm_f"], f, used, s["since"], cfg)
            s["level"] = new
            s["sum_exp"] += s["cin"] * epi_occ
            s["c15"] += (s["cin"] > 15.5) * epi_occ
            s["c55"] += (s["cin"] > 55.4) * epi_occ
            s["lvmin"][ar, used] += epi_t
            s["sw"] += (new != used) * epi_t
            if trace_n:
                for k, v in (("cin", s["cin"]), ("level", used), ("pm_f", s["pm_f"])):
                    tr[c][k][t] = v[:trace_n]
                if c == "C":
                    tr["sp"][t] = np.where(valid, sp, np.nan)[:trace_n]
                    tr["hr"][t] = np.where(valid, hr, np.nan)[:trace_n]
                    tr["flag"][t] = s["flag"][:trace_n]
                    tr["stress"][t] = stress[:trace_n]
        if trace_n:
            tr["cout"][t] = cout[:trace_n]

    # ---- metrik per run
    res = {}
    em = np.maximum(epi_min, 1.0)
    for c in controllers:
        s = st[c]
        oe = np.maximum(occ_epi_min, 1.0)
        m = dict(expo=s["sum_exp"] / oe, p15=100 * s["c15"] / oe, p55=100 * s["c55"] / oe,
                 energy=100 * (s["lvmin"] * speed ** 3).sum(1) / em,      # % daya kipas TURBO terus-menerus
                 flow=100 * (s["lvmin"] * speed).sum(1) / em,             # % aliran udara (proxy umur filter)
                 sw_day=s["sw"] / (em / 1440.0),
                 min_off=100 * s["lvmin"][:, 0] / em, min_turbo=100 * s["lvmin"][:, 3] / em)
        if c == "C":
            m.update(flag_pct=100 * s["fl_min"] / oe,
                     sens=np.where(s["st_min"] > 0, 100 * s["tp_min"] / np.maximum(s["st_min"], 1), np.nan),
                     fp_frac=np.where(s["fl_min"] > 0, 100 * s["fp_min"] / np.maximum(s["fl_min"], 1), np.nan),
                     youden=np.where((s["st_min"] > 0) & (oe - s["st_min"] > 0),
                                     s["tp_min"] / np.maximum(s["st_min"], 1)
                                     - s["fp_min"] / np.maximum(oe - s["st_min"], 1), np.nan),
                     false_onsets_day=s["on_false"] / (oe / 600.0),        # ~10 jam hunian/hari
                     baseline_ok=100 * s["have_min"] / oe)
        res[c] = m
    return res, tr


def simulate(n, scen, group, housing="terbuka", T_days=8, seed=0, controllers=CTRLS,
             trace_n=0, cfg=None, outdoor=None, chunk=150, force_bio_off=False):
    """Jalankan n run (dipecah per-chunk agar hemat memori)."""
    cfg = cfg or CFG
    if isinstance(scen, str):
        scen = SCENARIOS[scen]
    out, tr = None, None
    done = 0
    rng = np.random.default_rng(seed)
    while done < n:
        m = min(chunk, n - done)
        W = make_world(m, rng, scen, group, housing, T_days, cfg, outdoor)
        r, t_ = run_world(W, cfg, controllers, trace_n if done == 0 else 0, force_bio_off)
        tr = t_ if done == 0 else tr
        if out is None:
            out = {c: {k: [v] for k, v in r[c].items()} for c in controllers}
        else:
            for c in controllers:
                for k, v in r[c].items():
                    out[c][k].append(v)
        done += m
    out = {c: {k: np.concatenate(v) for k, v in out[c].items()} for c in controllers}
    return out, tr


# ===================================================================== ringkasan
def nmean(x):
    x = x[~np.isnan(x)]
    return float(x.mean()) if len(x) else float("nan")


def stat(x):
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    return (float(np.mean(x)), float(np.percentile(x, 5)), float(np.percentile(x, 95)))


def print_summary(name, group, n, res):
    print(f"\n=== skenario: {name} | grup: {group} | n={n} run ===")
    print(f"{'kontrol':8s}{'paparan':>10s}{'%mnt>15,5':>11s}{'%mnt>55,4':>11s}{'energi%':>9s}{'aliran%':>9s}{'ganti/hr':>10s}")
    for c in res:
        m = res[c]
        print(f"{c:8s}{m['expo'].mean():10.1f}{m['p15'].mean():11.1f}{m['p55'].mean():11.1f}"
              f"{m['energy'].mean():9.1f}{m['flow'].mean():9.1f}{m['sw_day'].mean():10.1f}")
    for a_, b_ in (("B", "A"), ("C", "B"), ("C", "D")):
        if a_ in res and b_ in res:
            de = stat(res[a_]["expo"] - res[b_]["expo"])
            dn = stat(res[a_]["energy"] - res[b_]["energy"])
            print(f"  Δ {a_}-{b_}: paparan {de[0]:+6.1f} [{de[1]:+.1f},{de[2]:+.1f}] ug/m3 | "
                  f"energi {dn[0]:+6.2f} [{dn[1]:+.2f},{dn[2]:+.2f}] poin%")
    if all(k in res for k in "BCD"):
        eB, eC, eD = (res[k]["energy"].mean() for k in "BCD")
        xB, xC, xD = (res[k]["expo"].mean() for k in "BCD")
        print(f"  C berada {100*(eC-eB)/max(eD-eB,1e-9):.0f}% di jalur energi B->D dan menutup "
              f"{100*(xB-xC)/max(xB-xD,1e-9):.0f}% selisih paparan B->D")
    if "C" in res:
        m = res["C"]
        print(f"  flag biometrik: aktif {nmean(m['flag_pct']):.1f}% menit-hunian | sensitivitas {nmean(m['sens']):.0f}% "
              f"| Youden J {nmean(m['youden']):+.2f} (0 = flag tanpa informasi, 1 = sempurna) | menit-flag palsu {nmean(m['fp_frac']):.0f}% | onset palsu/hari {nmean(m['false_onsets_day']):.2f} "
              f"| baseline siap {nmean(m['baseline_ok']):.0f}%")


def save_csv(path, rows):
    keys = ["skenario", "grup", "kontrol", "metrik", "mean", "p5", "p95"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        w.writerows(rows)


def collect_rows(name, group, res):
    rows = []
    for c in res:
        for k, v in res[c].items():
            rows.append([name, group, c] + [k] + [round(x, 3) for x in stat(v)])
    return rows


# ===================================================================== VERIFIKASI
def verify(seed=123):
    """Verifikasi = 'menyelesaikan persamaan dengan benar' (kode sesuai model). Jalankan SEBELUM validasi."""
    print("== VERIFIKASI ==")
    results = []

    def check(name, ok, info=""):
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {info}")

    rng = np.random.default_rng(seed)

    # V1: keadaan tunak model ruangan = solusi analitik
    a, P, k, S, lam = np.array([0.5, 4.0, 2.0]), np.array([0.9, 0.8, 1.0]), np.array([0.3, 0.2, 0.1]), np.array([0.0, 5.0, 0.0]), np.array([0.0, 4.0, 8.0])
    c = np.full(3, 10.0)
    for _ in range(3000):
        c = room_step(c, 100.0, a, P, k, S, lam)
    exact = (a * P * 100.0 + S) / (a + k + lam)
    check("V1 keadaan tunak = (aP*Cout+S)/(a+k+lam)", np.allclose(c, exact, rtol=1e-6), f"maks galat relatif {np.max(np.abs(c/exact-1)):.1e}")

    # V2: langkah eksak 1 menit konsisten dengan integrasi Euler halus dari ODE yang sama
    c0, ce = np.array([200.0]), np.array([200.0])
    aa, PP, kk, SS, ll = (np.array([x]) for x in (4.0, 0.9, 0.3, 0.0, 6.0))
    for _ in range(60):                                                  # 60 menit
        for _ in range(60):                                              # Euler dt = 1 detik
            ce = ce + (aa * PP * 50.0 - (aa + kk + ll) * ce + SS) / 3600.0
        c0 = room_step(c0, 50.0, aa, PP, kk, SS, ll)
    check("V2 langkah eksak ~ Euler 1-detik (60 menit)", np.allclose(c0, ce, rtol=2e-3), f"{c0[0]:.2f} vs {ce[0]:.2f}")

    # V3: kualitas pipeline sensor (NRMSE per jam vs PM sebenarnya), pembanding literatur [16]: 0,16-0,27
    scen = SCENARIOS["tanpa_respons"]
    W = make_world(120, rng, scen, "sehat", "terbuka", 8, CFG)
    T, n = W["T"], W["n"]
    cin, last = W["cin0"].copy(), W["cin0"].copy()
    tru, corr, raws = np.zeros((T, n)), np.zeros((T, n)), np.zeros((T, n))
    for t in range(T):
        cin = room_step(cin, W["cout"][t], W["a"], W["P"], W["k"], W["S"], 0.0)
        last = sensor_raw(cin, W["rh"][t], W["kappa"], W["s_bias"], W["gain"], W["pm_noise"][t], W["pm_drop"][t], last)
        tru[t], raws[t] = cin, last
        corr[t] = firmware_correct(last, W["rh"][t], CFG["firmware"]["kappa_est"], CFG["firmware"]["smoke_est"])
    H = T // 60
    th, ch, rh_ = (x[:H * 60].reshape(H, 60, n).mean(1) for x in (tru, corr, raws))
    mk = th > 35
    nr = lambda x: np.sqrt(np.mean((x[mk] - th[mk]) ** 2)) / np.mean(th[mk])
    check("V3 NRMSE per-jam sensor terkoreksi dalam kisaran wajar (0,08-0,40)", 0.08 <= nr(ch) <= 0.40,
          f"terkoreksi {nr(ch):.2f} | tanpa koreksi {nr(rh_):.2f} | acuan literatur 0,16-0,27")

    # V4: fisiologi dasar tanpa asap vs Tabel E
    sl = W["sleeping"] & ~W["walk"] if "walk" in W else W["sleeping"]
    sp_sleep = np.array([W["spo2_base"][W["sleeping"][:, i], i].mean() for i in range(n)])
    nadir = np.array([W["spo2_base"][W["sleeping"][:, i], i].min() for i in range(n)])
    hr_s = np.array([W["hr_base"][W["sleeping"][:, i] & ~W["rem"][:, i], i].mean() for i in range(n)])
    awake_rest = W["occupied"] & ~W["sleeping"] & W["still"]
    hr_a = np.array([W["hr_base"][awake_rest[:, i], i].mean() for i in range(n)])
    check("V4a SpO2 rerata semalam ~96 (95-97,5)", 95.0 <= sp_sleep.mean() <= 97.5, f"{sp_sleep.mean():.2f}")
    check("V4b nadir SpO2 semalam > 90 pada >= 85% run", np.mean(nadir > 90) >= 0.85, f"{100*np.mean(nadir>90):.0f}% run, median nadir {np.median(nadir):.1f}")
    check("V4c HR tidur (NREM) 5-20% di bawah HR bangun-diam", 0.78 <= np.mean(hr_s / hr_a) <= 0.97, f"rasio {np.mean(hr_s/hr_a):.2f}")

    # V5: hysteresis + hold timer meredam chatter di sekitar ambang
    nn, steps = 100, 1440
    sig = 14.0 + ar1(rng, steps, nn, 0.95, 2.0)
    def count_switches(cfg_):
        lvl, since, sw = np.zeros(nn, int), np.full(nn, 999.0), 0
        for t in range(steps):
            new, since = decide(sig[t], np.ones(nn), lvl, since, cfg_)
            sw += (new != lvl).sum()
            lvl = new
        return sw / nn / 24.0
    naive = dict(CFG, hyst=1.0, hold_down_min=0)
    sw_p, sw_n = count_switches(CFG), count_switches(naive)
    check("V5 hysteresis+hold mengurangi pergantian >= 60% vs tanpa keduanya", sw_p <= 0.4 * sw_n, f"{sw_p:.2f}/jam vs {sw_n:.2f}/jam")

    # V6: properti pasti -- tanpa data biometrik C == B; grup sehat A == B; determinisme
    r1, _ = simulate(30, "rentan_optimis", "rentan", seed=7, force_bio_off=True)
    check("V6a fail-safe: bio mati -> C identik dengan B", all(np.array_equal(r1["C"][m], r1["B"][m]) for m in ("expo", "energy", "sw_day")))
    r2, _ = simulate(30, "literatur_sehat", "sehat", seed=7)
    check("V6b grup sehat: A identik dengan B", all(np.array_equal(r2["A"][m], r2["B"][m]) for m in ("expo", "energy", "sw_day")))
    r3, _ = simulate(30, "literatur_sehat", "sehat", seed=7)
    check("V6c determinisme (seed sama -> hasil sama)", np.array_equal(r2["C"]["expo"], r3["C"]["expo"]))

    # V7: ambang lebih ketat tidak pernah menaikkan paparan rata-rata (D <= A), dan semua keluaran finite
    r4, _ = simulate(60, "tanpa_respons", "sehat", seed=11)
    check("V7a paparan D <= A (rata-rata berpasangan)", r4["D"]["expo"].mean() <= r4["A"]["expo"].mean(),
          f"A {r4['A']['expo'].mean():.1f} -> D {r4['D']['expo'].mean():.1f} ug/m3")
    fin = all(np.all(np.isfinite(v[np.isfinite(v)])) and not np.any(np.isinf(v)) for c_ in r4 for v in r4[c_].values())
    check("V7b tidak ada nilai tak-hingga/negatif tak wajar", fin and all((r4[c_]["expo"] >= 0).all() for c_ in r4))

    ok = all(results)
    print(f"== {sum(results)}/{len(results)} lulus ==")
    return ok


# ===================================================================== GRAFIK
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_trace(tr, path, title):
    plt = _plt()
    x = np.arange(tr["cout"].shape[0]) / 1440.0
    j = 0
    fig, ax = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    occ = tr["occ"][:, j]
    for a_ in ax:
        a_.fill_between(x, 0, 1, where=occ, transform=a_.get_xaxis_transform(), color="0.85", alpha=0.6, lw=0)
    ax[0].plot(x, tr["cout"][:, j], color="0.4", lw=1, label="luar")
    for c, col in zip(CTRLS, ("tab:blue", "tab:green", "tab:orange", "tab:red")):
        ax[0].plot(x, tr[c]["cin"][:, j], color=col, lw=0.8, label=f"dalam ({c})")
    for y in (15.5, 55.4):
        ax[0].axhline(y, color="k", ls=":", lw=0.6)
    ax[0].set_ylabel("PM2.5 (ug/m3)")
    ax[0].legend(ncol=5, fontsize=8, loc="upper right")
    ax[0].set_title(title + "   (area abu-abu = penghuni di kamar)")
    for c, col, off in (("A", "tab:blue", 0.0), ("C", "tab:orange", 0.08), ("D", "tab:red", 0.16)):
        ax[1].step(x, tr[c]["level"][:, j] + off, color=col, lw=0.8, label=f"level {c}")
    ax[1].set_yticks(range(4))
    ax[1].set_yticklabels(LEVELS)
    ax[1].legend(ncol=3, fontsize=8)
    ax[2].plot(x, tr["sp"][:, j], ".", ms=2, color="tab:purple")
    ax[2].set_ylabel("SpO2 terukur (%)")
    ax[3].plot(x, tr["hr"][:, j], ".", ms=2, color="tab:brown")
    ax[3].set_ylabel("HR terukur (bpm)")
    for a_ in ax[2:]:
        a_.fill_between(x, 0, 1, where=tr["flag"][:, j], transform=a_.get_xaxis_transform(), color="tab:orange", alpha=0.25, lw=0)
        a_.fill_between(x, 0, 0.06, where=tr["stress"][:, j], transform=a_.get_xaxis_transform(), color="tab:red", alpha=0.7, lw=0)
    ax[3].set_xlabel("hari  (oranye = flag biometrik aktif; garis merah bawah = stres fisiologis sebenarnya)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_pareto(store, path):
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(12, 5), sharey=False)
    cols = dict(A="tab:blue", B="tab:green", C="tab:orange", D="tab:red")
    marks = dict(zip(SCENARIOS, "osD^"))
    for ax, g in zip(axs, ("sehat", "rentan")):
        for sc in SCENARIOS:
            if (sc, g) not in store:
                continue
            r = store[(sc, g)]
            xs = [r[c]["energy"].mean() for c in "ABCD"]
            ys = [r[c]["expo"].mean() for c in "ABCD"]
            ax.plot(xs, ys, color="0.7", lw=0.8, zorder=1)
            for c, xx, yy in zip("ABCD", xs, ys):
                ax.scatter(xx, yy, color=cols[c], marker=marks[sc], s=55, zorder=2, edgecolor="k", lw=0.4)
        ax.set_title(f"grup {g}")
        ax.set_xlabel("energi kipas (% daya TURBO terus-menerus), makin kanan makin boros", fontsize=9)
        ax.set_ylabel("paparan rerata (ug/m3), makin tinggi makin buruk", fontsize=9)
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", ls="", color=cols[c], label=f"kontrol {c}") for c in "ABCD"]
    h += [Line2D([], [], marker=m, ls="", color="0.4", label=sc) for sc, m in marks.items()]
    axs[1].legend(handles=h, fontsize=8, loc="upper right")
    fig.suptitle("Paparan vs energi. C bernilai hanya bila jelas di bawah garis lurus B-D", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_sweep(grid_sp, grid_hr, M, lit, path, group):
    plt = _plt()
    fig, axs = plt.subplots(2, 2, figsize=(11, 8.5))
    spec = [("youden", "Informasi flag: Youden J = sensitivitas - laju alarm palsu (0 = tanpa informasi)", "RdBu_r", 0.0),
            ("sens", "Sensitivitas flag thd stres nyata (%)", "viridis", None),
            ("false_onsets_day", "Onset flag PALSU per hari", "magma_r", None),
            ("d_expo", "Manfaat paparan C-B (ug/m3; negatif = C lebih baik)", "PuOr", 0.0)]
    for ax, (key, ttl, cmap, center) in zip(axs.ravel(), spec):
        z = M[key]
        kw = {}
        if center is not None:
            m = np.nanmax(np.abs(z - center)) or 1.0
            kw = dict(vmin=center - m, vmax=center + m)
        im = ax.imshow(z.T, origin="lower", cmap=cmap, aspect="auto", **kw)
        ax.set_xticks(range(len(grid_sp)))
        ax.set_xticklabels(grid_sp)
        ax.set_yticks(range(len(grid_hr)))
        ax.set_yticklabels(grid_hr)
        ax.set_xlabel("respons SpO2 sebenarnya pada 150 ug/m3 (poin)")
        ax.set_ylabel("respons HR sebenarnya (bpm)")
        ax.set_title(ttl, fontsize=10)
        for i in range(len(grid_sp)):
            for j in range(len(grid_hr)):
                v = z[i, j]
                if np.isfinite(v):
                    rgba = im.cmap(im.norm(v))
                    lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                    ax.text(i, j, f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}", ha="center", va="center", fontsize=7,
                            color="w" if lum < 0.5 else "k")
        ni, nj = sum(g <= lit[0] for g in grid_sp), sum(g <= lit[1] for g in grid_hr)
        ax.add_patch(plt.Rectangle((-0.5, -0.5), ni, nj, fill=False, ec="lime", lw=2.5))
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle(f"Sapuan ukuran respons biometrik (grup {group}). Kotak hijau = batas atas literatur orang sehat "
                 f"(SpO2 <= {lit[0]} poin, HR <= {lit[1]} bpm)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ===================================================================== MODE JALAN
def run_mc(args):
    os.makedirs(args.out, exist_ok=True)
    store, rows = {}, []
    for sc in SCENARIOS:
        for g in ("sehat", "rentan"):
            t0 = time.time()
            res, _ = simulate(args.n, sc, g, args.housing, args.days, args.seed, outdoor=args.outdoor_series)
            store[(sc, g)] = res
            print_summary(sc, g, args.n, res)
            rows += collect_rows(sc, g, res)
            print(f"  ({time.time()-t0:.0f} dtk)")
    save_csv(os.path.join(args.out, "hasil_mc.csv"), rows)
    plot_pareto(store, os.path.join(args.out, "fig_pareto.png"))
    print(f"\nTersimpan: {args.out}/hasil_mc.csv, fig_pareto.png")


def run_demo(args):
    os.makedirs(args.out, exist_ok=True)
    sc = "rentan_optimis"
    res, tr = simulate(10, sc, "rentan", args.housing, args.days, args.seed, trace_n=1, outdoor=args.outdoor_series)
    plot_trace(tr, os.path.join(args.out, "fig_trace.png"), f"Satu run: skenario {sc}, grup rentan, rumah {args.housing}")
    print_summary(sc, "rentan", 10, res)
    print(f"\nTersimpan: {args.out}/fig_trace.png")


def run_sweep(args):
    os.makedirs(args.out, exist_ok=True)
    g_sp, g_hr = [0.0, 1.0, 2.0, 3.0, 5.0], [0.0, 4.0, 10.0, 15.0, 20.0]
    keys = ("youden", "sens", "false_onsets_day", "d_expo")
    M = {k: np.full((len(g_sp), len(g_hr)), np.nan) for k in keys}
    rows = []
    for i, v in enumerate(g_sp):
        for j, w in enumerate(g_hr):
            scen = dict(eff_spo2=(v, v), eff_hr=(w, w), tau_lat_h=(1.0, 6.0), mask=0.0)
            res, _ = simulate(args.n, scen, args.group, args.housing, args.days, args.seed,
                              controllers=("B", "C", "D"), outdoor=args.outdoor_series)
            C = res["C"]
            M["youden"][i, j], M["sens"][i, j] = nmean(C["youden"]), nmean(C["sens"])
            M["false_onsets_day"][i, j] = nmean(C["false_onsets_day"])
            M["d_expo"][i, j] = float(np.mean(C["expo"] - res["B"]["expo"]))
            rows.append([f"sp{v}_hr{w}", args.group, "C", "youden/sens/falseOn/dExpo"] +
                        [round(M[k][i, j], 3) for k in keys])
            print(f"  dSpO2={v:3.0f}  dHR={w:4.0f} | J {M['youden'][i,j]:+.2f}  sens {M['sens'][i,j]:.0f}%  "
                  f"onset palsu/hr {M['false_onsets_day'][i,j]:.2f}  C-B paparan {M['d_expo'][i,j]:+.2f}")
    plot_sweep(g_sp, g_hr, M, (1.0, 4.0), os.path.join(args.out, "fig_sweep.png"), args.group)
    with open(os.path.join(args.out, "hasil_sweep.csv"), "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["titik", "grup", "kontrol", "metrik", "youden", "sens", "onset_palsu_hari", "d_expo"])
        w_.writerows(rows)
    print(f"\nTersimpan: {args.out}/fig_sweep.png, hasil_sweep.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["verify", "demo", "mc", "sweep", "params", "all"])
    ap.add_argument("--n", type=int, default=150, help="jumlah run Monte Carlo per kombinasi (dokumen menyarankan >= 1000)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--housing", choices=["terbuka", "tertutup"], default="terbuka")
    ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--group", choices=["sehat", "rentan"], default="rentan", help="grup untuk mode sweep")
    ap.add_argument("--out", default="results")
    ap.add_argument("--outdoor", default=None, help="CSV satu kolom PM2.5 per jam (data nyata) menggantikan episode sintetis")
    args = ap.parse_args()
    args.outdoor_series = load_outdoor_csv(args.outdoor, args.days * 1440) if args.outdoor else None
    if args.mode == "params":
        print_param_table()
    if args.mode in ("verify", "all"):
        if not verify() and args.mode == "all":
            print("Verifikasi gagal -- hentikan sebelum validasi.")
            return
    if args.mode in ("demo", "all"):
        run_demo(args)
    if args.mode in ("mc", "all"):
        run_mc(args)
    if args.mode in ("sweep", "all"):
        run_sweep(args)


if __name__ == "__main__":
    main()
