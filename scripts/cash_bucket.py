"""Does a cash bucket used in down markets help? Bengen and the 8% guardrails plan.

Arms, for each base strategy:
  No cash        the original mix (e.g. 80/20)
  Static cash    cash held at a fixed share, rebalanced yearly (cash drag only)
  Cash bucket    same cash, but spent first (then bonds) while stocks are more than
                 --threshold below their peak, for up to --max-years; stocks are
                 not sold or rebalanced then; refilled by 1/--refill-years of the
                 target in each later year stocks rose.
Cash comes out of bonds (80/20 -> 80/10/10) and earns the T-bill rate.

    python scripts/cash_bucket.py
    python scripts/cash_bucket.py --cash 0.15 --threshold 0.2
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, bucket as bk  # noqa: E402

OUT = ROOT / "output" / "bucket"
HORIZON, FLOOR = 30, 4.0
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
ARM_COLORS = {"No cash": "#8a8984", "Static cash": "#86b6ef", "Cash bucket": "#2a78d6"}

# name, base rate, stocks, intl share, guardrail step (None = constant real), cap, drift
BASES = [
    ("Bengen: constant real, 50% US stocks", 0.040, 0.50, 0.0, None, None, 0.0),
    ("8% plan: guardrails ±30%, 80% stocks", 0.080, 0.80, 0.25, 0.30, 2.0, -0.005),
]


def windows(df):
    return [(list(df.stocks.loc[y:y + HORIZON - 1]), list(df.bonds.loc[y:y + HORIZON - 1]),
             list(df.bills.loc[y:y + HORIZON - 1]), list(df.inflation.loc[y:y + HORIZON - 1]), y)
            for y in range(df.index.min(), df.index.max() - HORIZON + 2)]


def sim(w, rate, base, cash, bucket, threshold, max_years, refill_years):
    _, _, stocks, _, step, cap, drift = base
    s, b, c, inf, _ = w
    if step is None:
        return bk.run(s, b, c, inf, rate, stocks, cash, bucket, threshold=threshold,
                      max_down_years=max_years, refill_years=refill_years)
    return bk.run(s, b, c, inf, rate, stocks, cash, bucket, step=step, floor=min(1.0, FLOOR / 100 / rate),
                  ceiling=cap, drift=drift, threshold=threshold, max_down_years=max_years,
                  refill_years=refill_years)


def failed(r, rate, base):
    if r["depleted"]:
        return True
    if base[4] is None:
        return False
    drift = base[6]
    return any(x * 100 < FLOOR * (1 + drift) ** k - 1e-9 for k, x in enumerate(r["reals"]))


def safe_rate(W, base, allow, **kw):
    grid = np.round(np.arange(0.03 if base[4] is None else FLOOR / 100, 0.15001, 0.0005), 5)
    best = np.nan
    for r in grid:
        if sum(failed(sim(w, r, base, **kw), r, base) for w in W) > allow:
            break
        best = r
    return best


def at_rate(W, base, rate, **kw):
    drift = base[6]
    plan = rate * 100 * (1 + drift) ** np.arange(HORIZON)
    rows = []
    for w in W:
        r = sim(w, rate, base, **kw)
        real = np.array(r["reals"]) * 100
        rows.append({"start_year": w[4], "ran_out": r["depleted"], "cut_vs_plan": max(0, (1 - real / plan).max()),
                     "spend_1_10": real[:10].mean(), "avg_spend": real.mean(), "final": r["final"] * 100,
                     "bucket_years": r["bucket_years"]})
    d = pd.DataFrame(rows)
    return {"typical_yrs_1_10": d.spend_1_10.median(), "typical_avg": d.avg_spend.median(),
            "cut_30_plus_or_ran_out": ((d.cut_vs_plan >= 0.30) | d.ran_out).mean(),
            "ran_out": int(d.ran_out.sum()), "median_final": d.final.median(), "worst_final": d.final.min(),
            "median_bucket_years": d.bucket_years.median()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cash", type=float, default=0.10)
    ap.add_argument("--threshold", type=float, default=0.10, help="downturn = stocks this far below peak")
    ap.add_argument("--max-years", type=int, default=5)
    ap.add_argument("--refill-years", type=int, default=5)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    base_df = data.load()
    base_df = base_df.assign(bonds=0.5 * base_df.bills + 0.5 * base_df.bonds)
    allow95 = math.floor(0.05 * 69 + 1e-9)
    common = dict(threshold=a.threshold, max_years=a.max_years, refill_years=a.refill_years)
    arms = {"No cash": dict(cash=0.0, bucket=False), "Static cash": dict(cash=a.cash, bucket=False),
            "Cash bucket": dict(cash=a.cash, bucket=True)}

    rows = []
    for base in BASES:
        W = windows(data.with_intl(base_df, base[3]))
        for arm, kw in arms.items():
            row = {"strategy": base[0], "arm": arm,
                   "safe_rate_100": safe_rate(W, base, 0, **kw, **common),
                   "safe_rate_95": safe_rate(W, base, allow95, **kw, **common)}
            row.update(at_rate(W, base, base[1], **kw, **common))
            rows.append(row)
        print(f"done {base[0]}", file=sys.stderr)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "cash_bucket_summary.csv", index=False)

    # sensitivity: cash size x trigger, safe rate (100%) for bucket vs static
    sens = []
    for base in BASES:
        W = windows(data.with_intl(base_df, base[3]))
        for cash in (0.05, 0.10, 0.15, 0.20, 0.30):
            if base[2] + cash > 1:
                continue
            sens.append({"strategy": base[0], "cash": cash, "rule": "Static cash",
                         "safe_rate": safe_rate(W, base, 0, cash=cash, bucket=False, **common)})
            for thr in (0.0, 0.10, 0.20):
                sens.append({"strategy": base[0], "cash": cash, "rule": f"Bucket, trigger {thr:.0%} below peak",
                             "safe_rate": safe_rate(W, base, 0, cash=cash, bucket=True, threshold=thr,
                                                    max_years=a.max_years, refill_years=a.refill_years)})
        print(f"sensitivity done {base[0]}", file=sys.stderr)
    sens = pd.DataFrame(sens)
    sens.to_csv(OUT / "cash_bucket_sensitivity.csv", index=False)

    # chart: change in the no-failure safe rate vs no cash, by cash size, for the chosen trigger
    trig_rule = f"Bucket, trigger {a.threshold:.0%} below peak"
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, base in zip(axes, BASES):
        no_cash = res[(res.strategy == base[0]) & (res.arm == "No cash")].safe_rate_100.values[0]
        d = sens[sens.strategy == base[0]]
        cashes = sorted(d.cash.unique())
        x = np.arange(len(cashes))
        for k, (rule, label, color) in enumerate(((("Static cash"), "Static cash, rebalanced yearly", "#86b6ef"),
                                                  (trig_rule, "Cash bucket (your rule)", "#2a78d6"))):
            v = [(d[(d.rule == rule) & (d.cash == c)].safe_rate.values[0] - no_cash) * 100 for c in cashes]
            bars = ax.bar(x + (k - 0.5) * 0.36, v, 0.34, color=color, label=label)
            for bb, vv in zip(bars, v):
                ax.text(bb.get_x() + bb.get_width() / 2, vv + (0.03 if vv >= 0 else -0.03), f"{vv:+.2f}",
                        ha="center", va="bottom" if vv >= 0 else "top", fontsize=8, color=INK)
        ax.axhline(0, color=INK, lw=1)
        ax.set_xticks(x, [f"{c:.0%}" for c in cashes])
        ax.set_xlabel("Cash share of portfolio (taken from bonds)", color=MUTED, fontsize=9)
        ax.set_title(f"{base[0]}\nno-cash safe start {no_cash:.2%}", loc="left", fontsize=10, color=INK)
        ax.set_ylim(-1, 1)
        ax.grid(axis="y", color=GRID_C, lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GRID_C)
        ax.tick_params(colors=MUTED, labelsize=8.5)
    axes[0].set_ylabel("Change in safe starting rate (points)", color=MUTED, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8.5, loc="lower left")
    fig.suptitle("A cash bucket barely moves the safe starting rate: at most +0.2 points", x=0.01, ha="left",
                 fontsize=12.5, color=INK)
    fig.text(0.01, 0.885, f"Highest starting rate with no failed retiree, 69 retirements 1928–1996, versus holding no "
             f"cash. Bucket: spend cash then bonds while stocks are {a.threshold:.0%}+ below peak (up to "
             f"{a.max_years} years), refill 1/{a.refill_years} in up years.", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(OUT / "cash_bucket.png", dpi=150)
    plt.close(fig)

    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(res.round(3).to_string(index=False))
        print()
        print(sens.pivot_table(index=["strategy", "rule"], columns="cash", values="safe_rate").round(3).to_string())


if __name__ == "__main__":
    main()
