"""Uji simulator. Jalankan: python -m pytest -q"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))

import simulator as S  # noqa: E402
from params import CFG  # noqa: E402


def test_naik_langsung_turun_setelah_hold():
    f = np.ones(1)
    lvl, since = S.decide(np.array([20.0]), f, np.zeros(1, int), np.array([999.0]), CFG)
    assert lvl[0] == 1 and since[0] == 0.0                      # 20 > 15,5 -> LOW, langsung
    lvl2, _ = S.decide(np.array([5.0]), f, lvl, np.array([5.0]), CFG)
    assert lvl2[0] == 1                                          # baru 5 menit: ditahan
    lvl3, _ = S.decide(np.array([5.0]), f, lvl, np.array([15.0]), CFG)
    assert lvl3[0] == 0                                          # 15 menit lewat: turun


def test_hysteresis_menahan_di_antara_ambang():
    f = np.ones(1)
    lvl = np.ones(1, int)
    # 14 ada di antara ambang-turun (12,4) dan ambang-naik (15,5): level tidak berubah
    out, _ = S.decide(np.array([14.0]), f, lvl, np.array([999.0]), CFG)
    assert out[0] == 1


def test_lantai_ambang_mencegah_kedip_di_udara_bersih():
    f = np.array([0.1])                                          # pengali ekstrem: 1,55 ug/m3 tanpa lantai
    below, _ = S.decide(np.array([9.0]), f, np.zeros(1, int), np.array([999.0]), CFG)
    above, _ = S.decide(np.array([11.0]), f, np.zeros(1, int), np.array([999.0]), CFG)
    assert below[0] == 0 and above[0] == 1                       # lantai LOW = 10


def test_determinisme():
    a, _ = S.simulate(8, "literatur_sehat", "sehat", T_days=3, seed=5)
    b, _ = S.simulate(8, "literatur_sehat", "sehat", T_days=3, seed=5)
    assert np.array_equal(a["C"]["expo"], b["C"]["expo"])


def test_grup_sehat_a_sama_dengan_b():
    r, _ = S.simulate(8, "literatur_sehat", "sehat", T_days=3, seed=1)
    assert np.array_equal(r["A"]["expo"], r["B"]["expo"])


def test_verifikasi_penuh():
    assert S.verify()
