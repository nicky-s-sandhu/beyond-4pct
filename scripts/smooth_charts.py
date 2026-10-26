"""Charts for the smooth-spending optimisation (run scripts/smooth_optimize.py first).

  smooth_pain.png        cut-severity levels: baselines vs optimised families vs the simple ratchet
  smooth_paths.png       real spending over the retirement: median, 10-90% band, worst retiree
  smooth_robustness.png  score under random nudges of the settings, and under other assumptions

    python scripts/smooth_charts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, vec  # noqa: E402

OUT = ROOT / "output" / "smooth"
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"]
LCOL = {"None": "#dcdbd5", "Mild": "#eda07a", "Moderate": "#dd7646", "Severe": "#bb5228", "Extreme": "#7f2f14",
        "Ran out": "#2b2a27"}
LLAB = {"None": "None (<5%)", "Mild": "Mild (5–15%)", "Moderate": "Moderate (15–30%)", "Severe": "Severe (30–50%)",
        "Extreme": "Extreme (≥50%)", "Ran out": "Ran out of money"}
SIMPLE = vec.Params(rate=0.048, stocks=1.0, intl=0.45, band=0.0, cut_step=0.0, raise_step=0.13, drift=-0.009)


def esc(s):
    return s.replace("$", r"\$")


def describe(p: vec.Params):
    bits = [f"{p.rate:.1%} start", f"{p.stocks:.0%} stocks ({p.intl:.0%} intl)"]
    if p.cut_step > 0 or p.raise_step > 0:
        bits.append(f"cut {p.cut_step:.1%} / raise {p.raise_step:.0%} outside ±{p.band:.0%}")
    if p.floor > 0:
        bits.append(f"floor {p.floor:.0%} of plan")
    if p.ceiling > 0:
        bits.append(f"cap {p.ceiling:.1f}×")
    if p.drift:
        bits.append(f"{p.drift:+.1%}/yr real")
    if p.cash > 0:
        bits.append(f"{p.cash:.0%} cash" + (f" bucket ({p.threshold:.0%} trigger)" if p.bucket else ""))
    return ", ".join(bits)


def style(ax):
    ax.grid(axis="y", color=GRID_C, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID_C)
    ax.tick_params(colors=MUTED, labelsize=8.5)


def main():
    chosen = {k: vec.Params(**v) for k, v in json.load(open(OUT / "chosen_params.json")).items()}
    order = [("Bengen 4% (50/50 US)", "Bengen 4%"), ("Previous 8% plan", "Previous 8% plan"),
             ("Constant real", "Optimised: constant real"), ("Guardrails", "Optimised: guardrails"),
             ("Guardrails + drift", "Optimised: guardrails + drift"), ("Everything", "Optimised: everything"),
             ("Simple ratchet", "Simple ratchet (no cuts)")]
    chosen["Simple ratchet"] = SIMPLE
    df = data.load()
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    sims, mets = {}, {}
    for key, _ in order:
        p = chosen[key]
        S = vec.windows(df, p.intl)
        sims[key] = vec.simulate(p, *S[1:])
        mets[key] = vec.metrics(p, sims[key])
    pd.DataFrame([{"strategy": lab, "settings": describe(chosen[k]),
                   **{m: v for m, v in mets[k].items() if m != "levels"}} for k, lab in order]) \
        .to_csv(OUT / "smooth_summary.csv", index=False)

    # ---- 1. pain levels
    n = len(order)
    fig = plt.figure(figsize=(13, 0.6 * n + 3.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 0.62], wspace=0.04)
    ax, axt = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    ypos = np.arange(n)[::-1]
    left = np.zeros(n)
    for lv in LEVELS:
        w = np.array([np.mean(mets[k]["levels"] == lv) * 100 for k, _ in order])
        bars = ax.barh(ypos, w, left=left, height=0.62, color=LCOL[lv], edgecolor="white", lw=1.5, label=LLAB[lv],
                       hatch="////" if lv == "Ran out" else None)
        for b, v, l0 in zip(bars, w, left):
            if v >= 7:
                ax.text(l0 + v / 2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", ha="center", va="center",
                        fontsize=8.5, color="white" if lv in ("Severe", "Extreme", "Ran out") else INK)
        left += w
    ax.axvline(90, color=INK, lw=1, ls=(0, (3, 3)))
    ax.text(90, n - 0.35, "10% extreme limit", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xlim(0, 100)
    ax.set_yticks(ypos, [lab for _, lab in order], fontsize=9, color=INK)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Share of 69 historical retirees, by deepest cut below plan", color=MUTED, fontsize=9)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    axt.set_xlim(0, 1)
    axt.set_ylim(ax.get_ylim())
    axt.axis("off")
    cols = [(0.03, "Smooth\nscore"), (0.24, "Start"), (0.42, "Typical\nyrs 1–10"), (0.64, "Typical\nlifetime"),
            (0.86, "Worst\nyear")]
    for x, h in cols:
        axt.text(x, n - 0.35, h, fontsize=8.5, color=MUTED, va="bottom")
    for y_, (k, _) in zip(ypos, order):
        m, p = mets[k], chosen[k]
        vals = [f"${m['ce']:.2f}", f"{p.rate:.1%}", f"${m['typical_1_10']:.2f}", f"${m['typical_avg']:.2f}",
                f"${m['worst_year']:.2f}"]
        for (x, _), v in zip(cols, vals):
            axt.text(x, y_, esc(v), va="center", fontsize=9.5, color=INK,
                     fontweight="bold" if x == 0.03 else "normal")
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, frameon=False, fontsize=8.5, bbox_to_anchor=(0.45, 0.0))
    best = max((mets[k]["ce"], lab) for k, lab in order)
    fig.suptitle("Optimising for smooth spending: no deep cuts, and a higher smooth-spending score than the 8% plan",
                 x=0.02, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.02, 0.93, esc("Smooth score = certainty-equivalent spending (risk aversion 3): the steady spending "
                             "worth the same as each plan's uneven outcomes. $ per $100 of starting portfolio, real."),
             fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.2, right=0.99, top=0.83, bottom=0.15)
    fig.savefig(OUT / "smooth_pain.png", dpi=150)
    plt.close(fig)

    # ---- 2. spending paths
    show = [("Bengen 4% (50/50 US)", "Bengen 4%"), ("Previous 8% plan", "Previous 8% plan"),
            ("Everything", "Optimised: everything"), ("Simple ratchet", "Simple ratchet (no cuts)")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.6), sharey=True)
    yrs = np.arange(1, 31)
    top = 0
    for ax, (k, lab) in zip(axes, show):
        R = sims[k]["reals"] * 100
        lo, med, hi = np.percentile(R, 10, axis=0), np.median(R, axis=0), np.percentile(R, 90, axis=0)
        worst = R[np.argmin(R.mean(axis=1))]
        ax.fill_between(yrs, lo, hi, color="#86b6ef", alpha=0.45, lw=0, label="10th–90th percentile")
        ax.plot(yrs, med, color="#2a78d6", lw=2.2, label="Median retiree")
        ax.plot(yrs, worst, color="#7f2f14", lw=1.4, ls=(0, (4, 2)), label="Lowest-spending retiree")
        ax.set_title(lab, loc="left", fontsize=10.5, color=INK)
        top = max(top, hi.max())
        ax.set_xlabel("Year of retirement", color=MUTED, fontsize=9)
        style(ax)
    axes[0].set_ylabel(esc("Real spending per $100 start ($)"), color=MUTED, fontsize=9)
    axes[0].set_ylim(0, np.ceil(top / 2) * 2 + 1)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    notes = {"Everything": "5.0% start · 100% stocks (45% intl) · 0.3% trim above start rate,\n13% raise below it · real −0.9%/yr",
             "Simple ratchet": "4.8% start · 100% stocks (45% intl) · never cut beyond\nthe −0.9%/yr plan · 13% raise below start rate",
             "Previous 8% plan": "8.0% start · 80% stocks · ±30% steps outside ±20% band\n\\$4 floor · −0.5%/yr",
             "Bengen 4% (50/50 US)": "4.0% start · 50/50 US · constant real"}
    for ax, (k, _) in zip(axes, show):
        ax.text(0.02, -0.25, notes[k], transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.suptitle("The optimised plans start lower than the 8% plan but rise instead of falling, with a narrow band",
                 x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(OUT / "smooth_paths.png", dpi=150)
    plt.close(fig)

    # ---- 3. robustness
    rj = pd.read_csv(OUT / "robust_joint.csv")
    fams = ["Constant real", "Guardrails", "Guardrails + drift", "Everything"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axes[0]
    rng = np.random.default_rng(0)
    for i, f in enumerate(fams):
        d = rj[rj.family == f]
        x = i + rng.uniform(-0.18, 0.18, len(d))
        ax.scatter(x[d.feasible], d.ce[d.feasible], s=7, color="#2a78d6", alpha=0.5, lw=0)
        ax.scatter(x[~d.feasible], d.ce[~d.feasible], s=7, color="#bb5228", alpha=0.6, lw=0)
        ax.scatter([i], [mets[f]["ce"]], s=60, marker="D", color=INK, zorder=3)
    ax.axhline(mets["Previous 8% plan"]["ce"], color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(3.5, mets["Previous 8% plan"]["ce"] + 0.05, "previous 8% plan", fontsize=8, color=MUTED, va="bottom")
    ax.axhline(4.0, color=MUTED, lw=1, ls=":")
    ax.text(3.5, 4.05, "Bengen 4%", fontsize=8, color=MUTED, va="bottom")
    ax.set_xticks(range(len(fams)), [f.replace(" + ", " + \n").replace("Constant real", "Constant\nreal")
                                     + f"\n{rj[rj.family == f].feasible.mean():.0%} within limit" for f in fams],
                  fontsize=8.5)
    ax.set_xlim(-0.5, 4.3)
    ax.set_ylim(2.8, 7.5)
    ax.set_ylabel(esc("Smooth score ($ per $100)"), color=MUTED, fontsize=9)
    ax.set_title("Settings nudged at random (±5% of each range, 400 tries)\n"
                 "◆ optimum · blue within the 10% limit · orange breaks it", loc="left", fontsize=10, color=INK)
    style(ax)

    ax = axes[1]
    runs = [("", "Main: risk aversion 3"), ("gamma2", "Risk aversion 2"), ("gamma5", "Risk aversion 5"),
            ("intl25", "International ≤25%"), ("intl_stress", "Pessimistic intl data"), ("us_only", "US stocks only")]
    rows = []
    for d, lab in runs:
        path = OUT / d if d else OUT
        r = pd.read_csv(path / "smooth_results.csv")
        r = r[r.family == "Everything"].iloc[0]
        p = vec.Params(**json.load(open(path / "chosen_params.json"))["Everything"])
        rows.append((lab, r.ce, p))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [r[1] for r in rows], color=["#2a78d6"] + ["#86b6ef"] * (len(rows) - 1), height=0.6)
    for yy, (lab, ce, p) in zip(y, rows):
        ax.text(ce + 0.05, yy, esc(f"${ce:.2f}  ·  {p.rate:.1%} start, {p.stocks:.0%} stocks, raise "
                                   f"{p.raise_step:.0%}, {p.drift:+.1%}/yr"), va="center", fontsize=8, color=INK)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=9, color=INK)
    ax.set_xlim(0, 12)
    ax.set_xlabel(esc("Smooth score of the re-optimised 'everything' plan ($ per $100)"), color=MUTED, fontsize=9)
    ax.set_title("Re-optimised under other assumptions: the same shape keeps winning", loc="left", fontsize=10,
                 color=INK)
    style(ax)
    ax.grid(axis="x", color=GRID_C, lw=0.8)
    ax.grid(axis="y", visible=False)
    fig.suptitle("How robust is the optimum?", x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "smooth_robustness.png", dpi=150)
    plt.close(fig)

    for k, lab in order:
        m = mets[k]
        print(f"{lab:32s} score ${m['ce']:.2f} | extreme {m['extreme_share']:.0%} | severe+ {m['severe_plus_share']:.0%}"
              f" | yrs1-10 ${m['typical_1_10']:.2f} | lifetime ${m['typical_avg']:.2f} | worst ${m['worst_year']:.2f}"
              f" | from-best ≥30% {m['cut_peak_30_share']:.0%} | median end ${m['median_final']:.0f} || "
              f"{describe(chosen[k])}")


if __name__ == "__main__":
    main()
