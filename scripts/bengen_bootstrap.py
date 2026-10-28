"""Bengen's 4% rule on reshuffled history.

For every retirement (the 69 real ones and 5,000 block-bootstrapped ones) compute the highest fixed real
withdrawal rate that lasts 30 years (Bengen's SAFEMAX), with year-end withdrawals and annual rebalancing as in
the replication. Reports the failure rate at 4% and the rate that 90/95/99% of retirements survive, by stock
share and by bootstrap block length.

    python scripts/bengen_bootstrap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import alt, data  # noqa: E402

T = 30


def frame(bonds="intermediate"):
    df = data.load(intl_series="intl")
    if bonds == "intermediate":
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    return df


def safemax(S, B, I, stocks):
    """Highest real rate (fraction of the starting portfolio) that lasts T years, per path.
    Balance after T years = G - w * sum_t price_t * growth after year t; set to zero."""
    r = stocks * S + (1 - stocks) * B
    growth = np.cumprod(1 + r[:, ::-1], axis=1)[:, ::-1]            # prod_{k>=t}(1+r_k)
    after = np.concatenate([growth[:, 1:], np.ones((len(r), 1))], axis=1)  # prod_{k>t}
    price = np.cumprod(np.concatenate([np.ones((len(r), 1)), 1 + I[:, :-1]], axis=1), axis=1)
    return growth[:, 0] / (price * after).sum(axis=1)


def paths(df, kind, block=10, n=5000, seed=7):
    if kind == "history":
        st = range(df.index.min(), df.index.max() - T + 2)
        idx = np.array([[df.index.get_loc(y + k) for k in range(T)] for y in st])
    else:
        idx = alt.bootstrap_index(len(df), n, T, block, seed)
    return df["stocks"].values[idx], df["bonds"].values[idx], df["inflation"].values[idx]


def summary(sm):
    return {"fail at 4%": f"{np.mean(sm < 0.04):.1%}", "worst": f"{sm.min():.2%}",
            "1% fail (99% safe)": f"{np.percentile(sm, 1):.2%}", "5% fail (95% safe)": f"{np.percentile(sm, 5):.2%}",
            "10% fail (90% safe)": f"{np.percentile(sm, 10):.2%}", "median": f"{np.median(sm):.2%}"}


def main():
    df = frame()
    rows = []
    for label, kind, block in [("Real history (69)", "history", 0), ("Reshuffled, 10-yr blocks", "boot", 10),
                               ("Reshuffled, 5-yr blocks", "boot", 5), ("Reshuffled, 20-yr blocks", "boot", 20),
                               ("Reshuffled, single years", "boot", 1)]:
        S, B, I = paths(df, kind, block)
        rows.append({"data": label, **summary(safemax(S, B, I, 0.5))})
    print("Bengen 50/50, intermediate bonds\n" + pd.DataFrame(rows).set_index("data").to_string())
    S, B, I = paths(df, "boot", 10)
    Sh, Bh, Ih = paths(df, "history")
    rows = []
    for st in (0.25, 0.4, 0.5, 0.6, 0.75, 1.0):
        sm, smh = safemax(S, B, I, st), safemax(Sh, Bh, Ih, st)
        rows.append({"stocks": f"{st:.0%}", "history worst": f"{smh.min():.2%}", **summary(sm)})
    print("\nBy stock share, reshuffled (10-yr blocks)\n" + pd.DataFrame(rows).set_index("stocks").to_string())
    d10 = frame("10y")
    S, B, I = paths(d10, "boot", 10); Sh, Bh, Ih = paths(d10, "history")
    print("\n10-year Treasuries, 50/50: history worst %.2f%%;" % (safemax(Sh, Bh, Ih, .5).min() * 100),
          summary(safemax(S, B, I, 0.5)))
    sm = safemax(*paths(df, "boot", 10), 0.5)
    np.save(ROOT / "output" / "alt" / "bengen_boot_safemax.npy", sm)


if __name__ == "__main__":
    main()
