"""Highest safe starting rate for each 30-year window, for the four zero-failure
variants of the summary ladder (Bengen's chart, extended).

"Safe" for a single retiree:
  Bengen       constant real spending never runs out in 30 years.
  Guardrails   real spending never drops below the $4 floor (declining with the
               drift when there is one) and the money never runs out.
For each start year the search returns the highest rate on a 0.1% grid such
that it and every lower rate is safe, so the minimum across start years equals
the variant's historical safe rate.

    python scripts/safemax_variants.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, strategies as st  # noqa: E402

OUT = ROOT / "output" / "variants"
HORIZON, TARGET = 30, 4.0
GRID = np.round(np.arange(0.030, 0.20001, 0.001), 4)

# (label, stocks, intl share, guardrail step, ceiling, drift); step None = Bengen
VARIANTS = [
    ("Bengen: constant real, 50/50 US", 0.5, 0.0, None, None, 0.0),
    ("+ guardrails ±30%, $4 floor, 80% stocks", 0.8, 0.0, 0.30, 2.0, 0.0),
    ("+ real spending −0.5%/yr", 0.8, 0.0, 0.30, 2.0, -0.005),
    ("+ 25% international stocks", 0.8, 0.25, 0.30, 2.0, -0.005),
]
# grey for the baseline, then an ordinal blue ramp (validated light >= step 250)
COLORS = ["#8a8984", "#86b6ef", "#2a78d6", "#104281"]
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"


def ok(rets, infl, rate, step, ceiling, drift):
    if step is None:
        d, *_ = st.fast_guardrails(rets, infl, rate, 0.0)
        return not d
    d, mn, *_ = st.fast_guardrails(rets, infl, rate, step, 0.2, min(1.0, TARGET / 100 / rate), ceiling,
                                   "end", drift, 10, drift)
    return (not d) and mn * 100 >= TARGET - 1e-9


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = data.load()
    base = base.assign(bonds=0.5 * base.bills + 0.5 * base.bonds)
    starts = list(range(base.index.min(), base.index.max() - HORIZON + 2))
    rows = []
    for label, stocks, intl, step, ceiling, drift in VARIANTS:
        df = data.with_intl(base, intl)
        rets = st.portfolio_returns(df, stocks)
        for y in starts:
            r_, i_ = list(rets.loc[y:y + HORIZON - 1]), list(df.inflation.loc[y:y + HORIZON - 1])
            best = np.nan
            grid = GRID if step is None else GRID[GRID >= TARGET / 100 - 1e-9]  # can't start below the floor
            for r in grid:
                if not ok(r_, i_, r, step, ceiling, drift):
                    break
                best = r
            rows.append({"variant": label, "start_year": y, "max_rate": best})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "safemax_by_start_year_variants.csv", index=False)

    fig, ax = plt.subplots(figsize=(11, 6.2))
    order = [v[0] for v in VARIANTS]
    mins = {}
    for label, color in zip(order, COLORS):
        s = res[res.variant == label]
        ax.plot(s.start_year, s.max_rate * 100, color=color, lw=2, label=label, zorder=3)
        w = s.loc[s.max_rate.idxmin()]
        mins[label] = w
        ax.scatter([w.start_year], [w.max_rate * 100], s=46, color=color, edgecolor="white", lw=1.5, zorder=4)
        left_side = w.start_year < 1964  # keep labels for neighbouring worst years apart
        ax.annotate(f"{w.max_rate:.1%}", (w.start_year, w.max_rate * 100), xytext=(-9 if left_side else 9, 0),
                    textcoords="offset points", ha="right" if left_side else "left", va="center",
                    fontsize=9, color=INK, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85), zorder=5)
    ax.axhline(4, color=MUTED, lw=1, ls=(0, (4, 4)), zorder=2)
    ax.set_xlim(starts[0] - 1, starts[-1] + 3)
    ax.set_ylim(3, res.max_rate.max() * 100 + 1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(axis="y", color=GRID_C, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID_C)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_ylabel("Highest safe starting rate", color=MUTED)
    ax.set_xlabel("Retirement start year (30-year window)", color=MUTED)
    lows = " → ".join(f"{mins[l].max_rate:.1%}" for l in order)
    fig.suptitle(f"Each change lifts the worst-year safe rate: {lows}", x=0.065, ha="left",
                 fontsize=13, color=INK, y=0.985)
    fig.text(0.065, 0.925, "Highest starting rate each retiree could have used. Bengen: never runs out. "
             "Guardrail variants: spending never below the $4 floor and never runs out. Dots = worst year.",
             fontsize=9, color=MUTED)
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "safemax_by_start_year_variants.png", dpi=150)
    plt.close(fig)

    summary = res.groupby("variant", sort=False).max_rate.agg(["min", "median", "max", "idxmin"])
    summary["worst_year"] = res.loc[summary["idxmin"], "start_year"].values
    print(summary.drop(columns="idxmin").to_string(float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
