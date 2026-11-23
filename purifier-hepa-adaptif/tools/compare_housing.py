#!/usr/bin/env python3
"""Bandingkan rumah berventilasi terbuka vs tertutup (skenario tanpa_respons, grup sehat)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))

import simulator as S  # noqa: E402

if __name__ == "__main__":
    print("Rumah    | kontrol A: paparan, %mnt>55,4 | kontrol D: paparan, %mnt>55,4")
    for housing in ("terbuka", "tertutup"):
        r, _ = S.simulate(150, "tanpa_respons", "sehat", housing, 8, seed=1)
        print(f"{housing:8s} | {r['A']['expo'].mean():6.1f} ug/m3, {r['A']['p55'].mean():4.0f}%   "
              f"| {r['D']['expo'].mean():6.1f} ug/m3, {r['D']['p55'].mean():4.0f}%")
