"""Charts for the alternative-strategy study (reads output/alt/final.json, writes output/alt/*.png)."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import alt  # noqa: E402
import alt_optimize as ao  # noqa: E402
import alt_robust as ar  # noqa: E402

OUT = ROOT / "output" / "alt"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e5e4df"
ACCENT, GHOST, BAD = "#2a78d6", "#8a8984", "#7f2f14"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False})

SIMPLE = alt.Alt(kind="guard", stocks0=0.85, intl=0.30, rate=0.053, drift=-0.035, gband=0.0, cut_step=0.025,
                 raise_step=0.15, floor=0.75)
LABEL = {
    "Recommended plan": "Recommended plan (6.1% start)",
    "History-tuned: CAPE amortization": "CAPE amortization, tuned on history",
    "History-tuned: recommended rule + glidepath": "Our rule + rising stocks, tuned on history",
    "Robust: recommended rule, re-tuned": "Our rule, robust re-tune (5.3% start)",
    "Robust: recommended rule + glidepath": "Our rule + rising stocks, robust",
    "Robust: amortization": "Amortization (TPAW/ABW-style), robust",
    "Robust: CAPE amortization": "CAPE amortization, robust",
    "Robust: percent of portfolio with limits": "Percent of portfolio with limits, robust",
    "Robust: amortization, floor-protected": r"Amortization with ~\$4 floor, robust",
    "Robust: CAPE amortization, floor-protected": r"CAPE amortization with ~\$4 floor, robust",
    "Vanguard dynamic, published (5%, +5%/-2.5%)": "Vanguard dynamic (published)",
    "ERN CAPE rule (1.75% + 0.5/CAPE), 75/25": "ERN CAPE rule (published)",
    "Bengen 4% (50/50 US)": "Bengen 4%",
}


def dumbbell(df):
    d = df[df.test.isin(["history", "bootstrap"])].pivot(index="strategy", columns="test", values="ce")
    d = d.loc[[k for k in LABEL if k in d.index]].sort_values("bootstrap")
    fig, ax = plt.subplots(figsize=(9, 6.2))
    y = np.arange(len(d))
    for i, (k, r) in enumerate(d.iterrows()):
        ax.plot([r.bootstrap, r.history], [i, i], color=GRID, lw=2, zorder=1)
    ax.scatter(d.history, y, s=60, color=GHOST, zorder=2, label="The 69 real retirements (1928–1996 starts)",
               edgecolor="white", linewidth=1.5)
    ax.scatter(d.bootstrap, y, s=60, color=ACCENT, zorder=3, label="5,000 reshuffled-history retirements",
               edgecolor="white", linewidth=1.5)
    for i, (k, r) in enumerate(d.iterrows()):
        ax.text(max(r.history, r.bootstrap) + 0.06, i, f"{r.bootstrap:.2f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [LABEL[k] for k in d.index])
    ax.axvline(d.loc["Recommended plan", "bootstrap"], color=ACCENT, lw=1, ls=":", zorder=0)
    ax.set_xlabel(r"Smooth-spending score (\$ per \$100 saved, survival-weighted, risk aversion 3)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_xlim(3.7, 7.0)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_title("Scores in real history vs out of history (label = out-of-history score)", loc="left",
                 fontsize=12, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "history_vs_bootstrap.png", dpi=150)


def frontier(df):
    Bs = ar.bootstrap()
    pts = []
    for rate in np.arange(0.048, 0.0625, 0.002):
        _, m = Bs.run(replace(SIMPLE, rate=float(rate)))
        pts.append((m["ran_out"] / 50, m["ce"], rate))
    b = df[df.test == "bootstrap"].set_index("strategy")
    fig, ax = plt.subplots(figsize=(9, 5.6))
    xs, ys, rs = zip(*pts)
    ax.plot(xs, ys, color=ACCENT, lw=2, marker="o", ms=5, label="Our rule, robust settings, by starting rate")
    for x, yv, r in pts:
        if round(r * 1000) % 4 == 0 or abs(r - 0.054) < 1e-9:
            ax.annotate(f"{r * 100:.1f}%", (x, yv), textcoords="offset points", xytext=(0, -15), ha="center",
                        fontsize=8, color=MUTED)
    show = {"Recommended plan": BAD, "Robust: amortization": INK, "Robust: CAPE amortization": INK,
            "Robust: amortization, floor-protected": GHOST, "Robust: percent of portfolio with limits": GHOST,
            "History-tuned: CAPE amortization": GHOST, "Bengen 4% (50/50 US)": GHOST,
            "Vanguard dynamic, published (5%, +5%/-2.5%)": GHOST}
    off = {"Recommended plan": (8, -4), "Robust: amortization": (8, -10), "Robust: CAPE amortization": (8, 4),
           "Robust: amortization, floor-protected": (8, -10), "Robust: percent of portfolio with limits": (10, 8),
           "History-tuned: CAPE amortization": (-8, 6), "Bengen 4% (50/50 US)": (8, -3),
           "Vanguard dynamic, published (5%, +5%/-2.5%)": (8, -3)}
    for k, c in show.items():
        r = b.loc[k]
        ax.scatter(r.ran_out_pct, r.ce, s=55, color=c, edgecolor="white", linewidth=1.5, zorder=3)
        dx, dy = off[k]
        lab = LABEL[k] + ("" if "below" in k else (f"\n{r.below4_pct:.0f}% ever below \\$3.90" if
                                                  k.startswith("Robust: amort") or k.startswith("Robust: CAPE")
                                                  or k.startswith("Robust: percent") else ""))
        ax.annotate(lab, (r.ran_out_pct, r.ce), textcoords="offset points", xytext=(dx, dy),
                    ha="right" if dx < 0 else "left", fontsize=8.5, color=INK)
    ax.set_xlabel("Ran out of money (% of 5,000 reshuffled-history retirements)")
    ax.set_ylabel(r"Smooth-spending score, out of history (\$)")
    ax.grid(color=GRID, lw=0.8)
    ax.set_xlim(-0.5, 24)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_title("Out of history, a lower start is both safer and scores better than 6.1%", loc="left",
                 fontsize=12, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "frontier.png", dpi=150)


def paths():
    Bs = ar.bootstrap()
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
    cands = [("Recommended plan (6.1% start)", ao.REC),
             ("Our rule, robust re-tune (5.3% start)", SIMPLE),
             ("Amortization, robust", None)]
    rows = json.loads((OUT / "final.json").read_text())
    amort = ar.to_alt([r for r in rows if r["strategy"] == "Robust: amortization"][0]["params"])
    cands[2] = ("Amortization (TPAW/ABW-style), robust", amort)
    yrs = np.arange(1, 31)
    for ax, (name, a) in zip(axes, cands):
        S = (1 - a.intl) * Bs.US + a.intl * Bs.INTL
        out = alt.simulate(a, S, Bs.B, Bs.I, Bs.K)
        R = out["reals"] * 100
        p10, p50, p90 = (np.percentile(R, q, axis=0) for q in (10, 50, 90))
        ax.fill_between(yrs, p10, p90, color="#86b6ef", alpha=0.5, lw=0, label="10th–90th percentile")
        ax.plot(yrs, p50, color=ACCENT, lw=2.5, label="Median")
        ax.plot(yrs, np.percentile(R, 5, axis=0), color=BAD, lw=1.5, ls="--", label="5th percentile")
        ax.axhline(4, color=MUTED, lw=1, ls=":")
        ax.text(30, 4.1, r"\$4", ha="right", fontsize=8, color=MUTED)
        ax.set_title(f"{name}\nran out: {out['depleted'].mean() * 100:.1f}%", loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Year of retirement")
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_ylim(0, 13)
    axes[0].set_ylabel(r"Real spending per \$100 saved (\$)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Spending across 5,000 reshuffled-history retirements", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "paths_bootstrap.png", dpi=150)


def plan_compare():
    """Earlier plan vs recommended plan across 5,000 reshuffled-history retirements (per $1M saved)."""
    sys.path.insert(0, str(ROOT / "app"))
    import model
    from bengen import vec
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    yrs = np.arange(1, 31)
    for ax, name, title in zip(axes, ["Earlier plan (6.1% start, 75% floor)", "Recommended plan"],
                               ["Earlier plan: 6.1% start, floor at 75% of year 1",
                                "Recommended: Blanchett curve, cap +10%, 2% risk target"]):
        s = model.PRESETS[name]
        p = model.to_params(s)
        US, INTL, B, C, I = model._boot(s["bonds"], s["intl_series"])
        out = vec.simulate(p, (1 - p.intl) * US + p.intl * INTL, B, C, I)
        R = out["reals"] * 1e3  # $k per $1M
        plan = p.plan(30) * 1e3
        lo, med, hi = (np.percentile(R, q, axis=0) for q in (10, 50, 90))
        ax.fill_between(yrs, lo, hi, color="#86b6ef", alpha=0.5, lw=0, label="10th–90th percentile")
        ax.plot(yrs, med, color=ACCENT, lw=2.5, label="Median")
        ax.plot(yrs, np.percentile(R, 5, axis=0), color=BAD, lw=1.5, ls="--", label="5th percentile")
        ax.plot(yrs, plan, color=MUTED, lw=1.2, ls=":", label="Planned path")
        if p.ceiling:
            ax.plot(yrs, plan * p.ceiling, color=MUTED, lw=1, label="Cap")
        floor = p.floor * p.rate * 1e3
        ax.axhline(floor, color=INK, lw=1, ls=(0, (6, 3)), label="Floor")
        ax.set_title(f"{title}\nran out: {out['depleted'].mean():.1%} of 5,000", loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Year of retirement")
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_ylim(0, 130)
    axes[0].set_ylabel(r"Real spending per \$1M saved (\$ thousands)")
    axes[1].legend(loc="upper right", frameon=False, fontsize=8, ncol=2)
    fig.suptitle("Spending across 5,000 retirements reshuffled from real history", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "plan_compare.png", dpi=150)


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv(OUT / "final_robust.csv")
    dumbbell(df)
    frontier(df)
    paths()
    plan_compare()
