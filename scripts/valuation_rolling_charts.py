"""Charts for the sliding-vs-10-year-average experiment (output/valuation/rolling_*.png)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import valuation as V  # noqa: E402

OUT = ROOT / "output" / "valuation"
INK, MUTED, GRID, ACCENT, BAD, GHOST = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#7f2f14", "#8a8984"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
ORDER = ["Fixed 60%", "Best single stock share", "Pfau-Kitces 60/45/30", "Sliding vs 10-year average (new)",
         "Optimised 3 levels vs median to date"]
LABEL = {"Fixed 60%": "Fixed 60%", "Best single stock share": "Best single\nstock share",
         "Pfau-Kitces 60/45/30": "Pfau-Kitces\n60/45/30", "Sliding vs 10-year average (new)": "Sliding vs\n10-yr average",
         "Optimised 3 levels vs median to date": "3 levels vs\nmedian to date"}


def comparison():
    a = pd.read_csv(OUT / "rolling_in_sample.csv"); b = pd.read_csv(OUT / "rolling_out_of_sample.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), sharey=True)
    for ax, safe in zip(axes, ("bills", "bonds")):
        ins = a[a.safe == safe].set_index("rule")["SAFEMAX %"]
        wf = b[(b.safe == safe) & (b.test.str.startswith("walk"))].set_index("rule")["test SAFEMAX %"]
        x = np.arange(len(ORDER))
        ax.bar(x - 0.19, [ins[r] for r in ORDER], 0.36, color=GHOST, label="In sample, starts 1890–1993")
        ax.bar(x + 0.19, [wf[r] for r in ORDER], 0.36, color=[ACCENT if r.startswith("Sliding") else "#86b6ef" for r in ORDER],
               label="Walk-forward, starts 1950–1993")
        for xi, r in zip(x, ORDER):
            ax.text(xi + 0.19, wf[r] + 0.04, f"{wf[r]:.2f}", ha="center", fontsize=8.5)
            ax.text(xi - 0.19, ins[r] + 0.04, f"{ins[r]:.2f}", ha="center", fontsize=8.5, color=MUTED)
        ax.set_xticks(x, [LABEL[r] for r in ORDER], fontsize=8.5); ax.set_ylim(3, 5.3)
        ax.set_title(f"Stocks + {safe}", loc="left", fontsize=11, color=INK); ax.grid(axis="y", color=GRID, lw=0.8)
    axes[0].set_ylabel("SAFEMAX (%)"); axes[0].legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.suptitle("Judging CAPE against its 10-year average: worst-case safe rate", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "rolling_comparison.png", dpi=150)


def timeline():
    d = V.load()
    p = json.loads((OUT / "rolling_params.json").read_text())["bills|Sliding vs 10-year average (new)"]
    q = json.loads((OUT / "rolling_params.json").read_text())["bills|Optimised 3 levels vs median to date"]
    yrs = d.index[d["cape_rel10"].notna()]
    r10, rm = d.loc[yrs, "cape_rel10"].values, d.loc[yrs, "cape_rel"].values
    s_new = V.ramp_shares(r10, p["s_min"], p["s_max"], p["s_mid"], p["width"]) * 100
    s_old = np.where(rm < 2 / 3, q["u"], np.where(rm > 4 / 3, q["o"], q["f"])) * 100
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]})
    ax = axes[0]
    ax.plot(yrs, d.loc[yrs, "cape_jan"], color=INK, lw=1.4, label="CAPE (January)")
    ax.plot(yrs, d.loc[yrs, "cape_avg10"], color=ACCENT, lw=1.4, ls="--", label="Its 10-year average ('normal')")
    ax.plot(yrs, d.loc[yrs, "cape_median"], color=GHOST, lw=1.2, ls=":", label="Its median to date")
    ax.set_ylabel("CAPE"); ax.grid(axis="y", color=GRID, lw=0.8); ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_title("Stock share (stocks + bills) under the optimised sliding rule vs the 3-level rule", loc="left",
                 fontsize=11, color=INK)
    ax = axes[1]
    ax.step(yrs, s_old, where="post", color=GHOST, lw=1.2, label="3 levels vs median to date (100/55/5)")
    ax.fill_between(yrs, s_new, step="post", color=ACCENT, alpha=0.3, lw=0)
    ax.step(yrs, s_new, where="post", color=ACCENT, lw=1.4,
            label=f"Sliding vs 10-yr average ({p['s_max']:.0%} → {p['s_mid']:.0%} → {p['s_min']:.0%})")
    ax.set_ylabel("Stock share (%)"); ax.set_ylim(0, 105); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=1)
    fig.tight_layout(); fig.savefig(OUT / "rolling_timeline.png", dpi=150)


if __name__ == "__main__":
    comparison(); timeline()
