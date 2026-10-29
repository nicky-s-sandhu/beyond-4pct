"""Reproduce Pfau and Kitces (2015), "Retirement Risk, Rising Equity Glide Paths, and Valuation-Based Asset
Allocation", Journal of Financial Planning 28 (3): 38-48.

Shiller data, retirements starting each January 1881-1984 (30 years ending by 2013, as in the paper), fixed real
withdrawals at the start of each year, annual rebalancing, stocks paired with bills or with 10-year Treasuries.

    python scripts/repro_pfau_kitces.py            # writes output/valuation/pfau_kitces_*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import valuation as V  # noqa: E402

OUT = ROOT / "output" / "valuation"
STARTS = list(range(1881, 1985))
STATES = ["Undervalued", "Fair", "Overvalued"]

# Figures stated in the paper's text and in CXO Advisory's summary of it (tables are images)
PUBLISHED = {
    ("Fixed 60%", "bonds", "All"): 3.62,
    ("Accel. rising 30→60 (15 yrs)", "bills", "All"): 4.21,
    ("Declining 60→30 (30 yrs) + valuation, unbounded", "bills", "Undervalued"): 5.80,
    ("Valuation 30/45/60", "bills", "Fair"): 4.50,
    ("Accel. rising 30→60 (15 yrs) + valuation, unbounded", "bills", "Overvalued"): 4.23,
}


def run(d=None, starts=STARTS):
    d = V.load() if d is None else d
    rows = []
    for safe in ("bills", "bonds"):
        S, B, rel = V.windows(d, starts, safe=safe)
        st = V.state(rel[:, 0])
        for name, strat in V.kp_strategies().items():
            R, w = V.path_returns(strat, S, B, rel)
            sm, tw = V.safemax(R) * 100, V.terminal_wealth(R)
            row = {"strategy": name, "safe": safe, "All": sm.min(), "worst_start": starts[int(np.argmin(sm))],
                   "median_wealth_All": np.median(tw), "avg_stocks": w.mean() * 100}
            for s in STATES:
                k = st == s
                row[s] = sm[k].min()
                row[f"median_wealth_{s}"] = np.median(tw[k])
            rows.append(row)
    df = pd.DataFrame(rows)
    counts = pd.Series(st).value_counts().reindex(STATES)
    return df, counts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df, counts = run()
    df.to_csv(OUT / "pfau_kitces_repro.csv", index=False)
    print("Retirements by starting valuation:", counts.to_dict())
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.precision", 2):
        for safe in ("bills", "bonds"):
            print(f"\nSAFEMAX (%) with stocks + {safe}")
            print(df[df.safe == safe].set_index("strategy")[["All", "worst_start"] + STATES + ["avg_stocks"]])
        print("\nMedian real wealth after 30 years at 4% (start $100)")
        print(df.pivot(index="strategy", columns="safe", values="median_wealth_All").round(0))
    print("\nPublished vs reproduced")
    for (name, safe, col), pub in PUBLISHED.items():
        ours = df[(df.strategy == name) & (df.safe == safe)][col].iloc[0]
        print(f"  {name:55s} {safe:5s} {col:11s} published {pub:.2f}%  ours {ours:.2f}%")


if __name__ == "__main__":
    main()
