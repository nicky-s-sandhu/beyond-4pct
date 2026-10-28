"""Out-of-sample checks for the rules found by alt_optimize.py.

1. Split sample: rules optimised on 1928-1962 starts, scored on 1963-1996 starts.
2. Earlier US history: 1872-1927 starts (Jorda-Schularick-Taylor data, US stocks only).
3. Fifteen other countries, 1871-1991 starts, home-country stocks and bonds (rules without CAPE).
4. Recent US retirees with incomplete windows (1997-2010 starts, data to 2025).
5. Starting rate each rule would set today (CAPE ~40 in Oct 2026).
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alt_engine as E  # noqa: E402
from bengen import vec  # noqa: E402

OUT = E.ROOT / "output" / "alt"
W = vec.survival_weights(who="couple")
KEYS = ["ce", "start", "typical_1_10", "typical_11_20", "typical_21_30", "extreme_share", "ran_out",
        "giveback_30_share", "cuts_5_per_retiree", "worst_year", "median_final", "n"]


def load(name):
    return {k: E.Rule(**v) for k, v in json.load(open(OUT / name / "rules.json")).items()}


def row(label, rule, w, **extra):
    m = E.evaluate(rule, w, W)
    return {"rule": label, **extra, **{k: m[k] for k in KEYS}}


def main():
    rules = load("main")
    early = load("train_early")
    rows = []
    # 1. split sample
    for label, r in early.items():
        rows.append(row(label, r, E.us_windows(r.intl, 1963, 1996), test="US 1963-1996 (trained 1928-1962)"))
        rows.append(row(label, r, E.us_windows(r.intl, 1928, 1962), test="US 1928-1962 (in sample)"))
    # 2. earlier US
    w_us_early = E.jst_windows("USA", 1872, 1927, cape=True)
    for label, r in rules.items():
        rows.append(row(label, replace(r, intl=0.0), w_us_early, test="US 1872-1927 (US stocks only)"))
    # 3. other countries (non-CAPE rules)
    for c in ["Australia", "Belgium", "Canada", "Switzerland", "Germany", "Denmark", "Spain", "Finland", "France",
              "UK", "Italy", "Japan", "Netherlands", "Norway", "Sweden"]:
        w = E.jst_windows(c, 1871, 1991)
        if w is None:
            continue
        for label, r in rules.items():
            if r.cape_b > 0 or r.cape_slope > 0:
                continue
            rows.append(row(label, replace(r, intl=0.0), w, test=f"Country: {c}"))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "out_of_sample.csv", index=False)

    # 4. recent retirees, partial windows
    recent = []
    for y in range(1997, 2011):
        n_years = 2025 - y + 1
        E.T = n_years
        for label, r in rules.items():
            from bengen import data
            df_ = data.load(intl_series="intl")
            df_ = df_.assign(bonds=0.5 * df_.bills + 0.5 * df_.bonds)
            cape = pd.read_csv(E.ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
            st = (1 - r.intl) * df_.stocks + r.intl * df_.intl
            sl = slice(y, 2025)
            w = {"S": st.loc[sl].values[None], "B": df_.bonds.loc[sl].values[None], "C": df_.bills.loc[sl].values[None],
                 "I": df_.inflation.loc[sl].values[None], "cape": cape.loc[sl].values[None]}
            o = E.simulate(r, w)
            R = o["reals"][0] * 100
            recent.append({"start": y, "rule": label, "years": n_years, "first": R[0], "lowest": R.min(),
                           "latest": R[-1], "avg": R.mean(), "balance_now": o["balances"][0, -1] * 100,
                           "max_giveback": float((1 - (R / o["planf"]) / np.maximum.accumulate(R / o["planf"])).max()),
                           "path": [round(x, 3) for x in R]})
    E.T = 30
    pd.DataFrame(recent).to_csv(OUT / "recent_retirees.csv", index=False)

    # 5. starting rate today
    today = []
    for cape_now in (17.0, 25.0, 30.0, 40.0):
        for label, r in rules.items():
            w = {"S": np.zeros((1, 30)), "B": np.zeros((1, 30)), "C": np.zeros((1, 30)), "I": np.zeros((1, 30)),
                 "cape": np.full((1, 30), cape_now)}
            today.append({"cape": cape_now, "rule": label, "start_rate": float(E.simulate(r, w)["rate0"][0]) * 100})
    pd.DataFrame(today).to_csv(OUT / "start_rate_by_cape.csv", index=False)


if __name__ == "__main__":
    main()
