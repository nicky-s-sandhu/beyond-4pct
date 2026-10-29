"""Charts for the slow-bend (duration) experiment (output/valuation/duration_*.png)."""
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
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from bengen import valuation as V  # noqa: E402
import valuation_duration as vd  # noqa: E402

OUT = ROOT / "output" / "valuation"
INK, MUTED, GRID, ACCENT, BAD, GHOST = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#7f2f14", "#8a8984"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
ORDER = ["Fixed 60%", "Pfau-Kitces 60/45/30", "Sliding vs 10-year average (new)", "Optimised 3 levels vs median to date",
         "Slow bend, 10-year ramp (new)"]
LABEL = {"Fixed 60%": "Fixed 60%", "Pfau-Kitces 60/45/30": "Pfau-Kitces\n60/45/30",
         "Sliding vs 10-year average (new)": "Sliding vs\n10-yr average", "Optimised 3 levels vs median to date":
         "3 levels vs\nmedian to date", "Slow bend, 10-year ramp (new)": "Slow bend\n(10-yr ramp)"}


def comparison():
    o = pd.read_csv(OUT / "duration_out_of_sample.csv")
    wf = o[o.test.str.startswith("walk")]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for ax, metric, title in ((axes[0], "test SAFEMAX %", "Worst-case safe rate (SAFEMAX)"),
                              (axes[1], "test median MWR %", "Typical retiree's highest safe rate")):
        x = np.arange(len(ORDER))
        for k, safe in enumerate(("bills", "bonds")):
            s = wf[wf.safe == safe].set_index("rule")[metric]
            vals = [s[r] for r in ORDER]
            ax.bar(x + (k - 0.5) * 0.38, vals, 0.36, color=[ACCENT, "#86b6ef"][k], label=f"Stocks + {safe}")
            for xi, v in zip(x, vals):
                ax.text(xi + (k - 0.5) * 0.38, v + 0.05, f"{v:.2f}", ha="center", fontsize=8)
        ax.set_xticks(x, [LABEL[r] for r in ORDER], fontsize=8.5)
        ax.set_ylim(3, 7.6 if "median" in metric else 5.6)
        ax.set_title(title, loc="left", fontsize=11, color=INK); ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_ylabel("%")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle("Walk-forward test, retirements starting 1950–1993 (settings chosen only from earlier retirements)",
                 x=0.01, ha="left", fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "duration_comparison.png", dpi=150)


def timeline():
    p = json.loads((OUT / "duration_params.json").read_text())["bills"]["ramp 10"]
    run, _ = vd.states(p["hi"], p["decay"])
    w = vd.duration_shares(run, vd.REL_ALL, p) * 100
    rel = vd.REL_ALL
    yrs = rel.index
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [1, 0.7, 1]})
    ax = axes[0]
    ax.plot(yrs, rel, color=INK, lw=1.3)
    ax.axhline(p["hi"], color=BAD, lw=1, ls="--"); ax.axhline(2 / 3, color=ACCENT, lw=1, ls="--")
    ax.text(1882, p["hi"] + 0.07, f"elevated: above {p['hi']:.2f}x median", color=BAD, fontsize=8.5)
    ax.text(1882, 2 / 3 - 0.22, "cheap: below 2/3 of median", color=ACCENT, fontsize=8.5)
    ax.set_ylabel("CAPE ÷ median to date"); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_title(f"Slow bend (stocks + bills): {p['s_normal']:.0%} normally, down to {p['s_min']:.0%} after "
                 f"{p['ramp']} elevated years, {p['s_max']:.0%} when cheap", loc="left", fontsize=11, color=INK)
    ax = axes[1]
    ax.bar(yrs, run, color=BAD, width=0.9)
    ax.axhline(p["ramp"], color=MUTED, lw=1, ls=":"); ax.text(1882, p["ramp"] + 1, "fully bent", fontsize=8.5, color=MUTED)
    ax.set_ylabel("Elevated-years count"); ax.grid(axis="y", color=GRID, lw=0.8)
    ax = axes[2]
    ax.fill_between(yrs, w, step="post", color=ACCENT, alpha=0.3, lw=0)
    ax.step(yrs, w, where="post", color=ACCENT, lw=1.3)
    ax.set_ylabel("Stock share (%)"); ax.set_ylim(0, 105); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.annotate("0% stocks from 2001 on", xy=(2015, 2), xytext=(1988, 80), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=MUTED))
    fig.tight_layout(); fig.savefig(OUT / "duration_timeline.png", dpi=150)


if __name__ == "__main__":
    comparison(); timeline()


def fifty():
    df = pd.read_csv(OUT / "duration50.csv")
    order = ["Fixed 60%", "Fixed 75%", "Slow bend 0-100% (previous)", "Slow bend 50-100%, 10-yr ramp (new)"]
    lab = {"Fixed 60%": "Fixed 60%", "Fixed 75%": "Fixed 75%", "Slow bend 0-100% (previous)": "Slow bend\n0–100%",
           "Slow bend 50-100%, 10-yr ramp (new)": "Slow bend\n50–100%"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    panels = [("walk-forward SAFEMAX %", "Worst case, walk-forward (%)", (3, 5.5)),
              ("walk-forward median MWR %", "Typical retiree, walk-forward (%)", (3, 7.6)),
              (None, "Recent retirees: real wealth Jan 2023\n(avg of 1995, 2000, 2005, 2010 starts, per \\$100)", (0, 200))]
    x = np.arange(len(order))
    for ax, (col, title, ylim) in zip(axes, panels):
        for k, safe in enumerate(("bills", "bonds")):
            s = df[df.safe == safe].set_index("rule")
            vals = [s.loc[r, col] if col else s.loc[r, [c for c in s.columns if c.startswith("wealth 2023")]].mean()
                    for r in order]
            ax.bar(x + (k - 0.5) * 0.38, vals, 0.36, color=[ACCENT, "#86b6ef"][k], label=f"Stocks + {safe}")
            for xi, v in zip(x, vals):
                ax.text(xi + (k - 0.5) * 0.38, v + (0.04 if col else 3), f"{v:.2f}" if col else f"{v:.0f}",
                        ha="center", fontsize=8)
        ax.set_xticks(x, [lab[r] for r in order], fontsize=8.5); ax.set_ylim(*ylim)
        ax.set_title(title, loc="left", fontsize=10, color=INK); ax.grid(axis="y", color=GRID, lw=0.8)
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle("Slow bend with stocks held between 50% and 100%", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "duration50.png", dpi=150)
