#!/usr/bin/env python3
"""Bangkitkan vektor uji dari simulator Python untuk menguji firmware C++ (firmware/host_test/host_test.cpp).

Tujuannya: membuktikan bahwa logika kontrol di firmware menghasilkan keputusan yang SAMA dengan
logika yang sudah diverifikasi di simulator.

Keluaran di firmware/host_test/vectors/:
  decide.csv      5000 kasus acak fungsi decide()
  correct.csv     3000 kasus acak koreksi RH + asap
  seq_f1.csv      deret 8 hari menit-per-menit, kontroler A (pengali ambang 1,0)
  seq_f06.csv     deret yang sama, pengali ambang 0,6 (profil rentan)
  seq_init.txt    nilai awal pm_f
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))

import simulator as S  # noqa: E402
from params import CFG, SCENARIOS  # noqa: E402

OUT = ROOT / "firmware" / "host_test" / "vectors"


def g(x):
    return f"{float(x):.17g}"


def gen_decide(n=5000, seed=1):
    rng = np.random.default_rng(seed)
    pm = np.exp(rng.uniform(np.log(1.0), np.log(400.0), n))
    f = rng.choice([1.0, 0.7, 0.6, 0.42], n)
    level = rng.integers(0, 4, n)
    since = rng.choice([0.0, 1.0, 5.0, 14.0, 15.0, 16.0, 40.0, 999.0], n)
    new, new_since = S.decide(pm, f, level, since, CFG)
    with open(OUT / "decide.csv", "w") as fh:
        fh.write("pm_f,f,level,since,new_level,new_since\n")
        for i in range(n):
            fh.write(f"{g(pm[i])},{g(f[i])},{level[i]},{g(since[i])},{new[i]},{g(new_since[i])}\n")


def gen_correct(n=3000, seed=2):
    rng = np.random.default_rng(seed)
    raw = np.round(rng.uniform(0, 800, n))
    rh = rng.uniform(35, 99.5, n)
    fw = CFG["firmware"]
    exp = S.firmware_correct(raw, rh, fw["kappa_est"], fw["smoke_est"])
    with open(OUT / "correct.csv", "w") as fh:
        fh.write("raw,rh,expected\n")
        for i in range(n):
            fh.write(f"{g(raw[i])},{g(rh[i])},{g(exp[i])}\n")


def gen_sequences(seed=3):
    rng = np.random.default_rng(seed)
    W = S.make_world(1, rng, SCENARIOS["tanpa_respons"], "sehat", "terbuka", 8, CFG)
    fw = CFG["firmware"]
    alpha = 1 - np.exp(-1.0 / CFG["ema_pm_min"])
    ar = np.arange(1)
    first = True
    for name, fval in (("seq_f1.csv", 1.0), ("seq_f06.csv", 0.6)):
        cin, last, pm_f = W["cin0"].copy(), W["cin0"].copy(), W["cin0"].copy()
        level, since, f = np.zeros(1, int), np.full(1, 999.0), np.full(1, fval)
        if first:
            (OUT / "seq_init.txt").write_text(g(pm_f[0]) + "\n")
            first = False
        with open(OUT / name, "w") as fh:
            fh.write("raw,rh,pm_f,level\n")
            for t in range(W["T"]):
                lam = W["lam_lv"][ar, level]
                cin = S.room_step(cin, W["cout"][t], W["a"], W["P"], W["k"], W["S"], lam)
                raw = S.sensor_raw(cin, W["rh"][t], W["kappa"], W["s_bias"], W["gain"],
                                   W["pm_noise"][t], W["pm_drop"][t], last)
                last = raw
                corr = S.firmware_correct(raw, W["rh"][t], fw["kappa_est"], fw["smoke_est"])
                pm_f = pm_f + alpha * (corr - pm_f)
                level, since = S.decide(pm_f, f, level, since, CFG)
                fh.write(f"{g(raw[0])},{g(W['rh'][t][0])},{g(pm_f[0])},{level[0]}\n")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    gen_decide()
    gen_correct()
    gen_sequences()
    print(f"Vektor uji ditulis ke {OUT}")
