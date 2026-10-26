"""Charts for the spending-smile optimisation (run scripts/smile_optimize.py first).

  smile_pain.png        cut severity (below plan, and from best year) with decade spending
  smile_paths.png       real spending by year: median, 10-90% band, lowest retiree, plan
  smile_robustness.png  random nudges of the settings; re-optimised under other assumptions

    python scripts/smile_charts.py
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
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import data, vec  # noqa: E402
import smooth_optimize as so  # noqa: E402

OUT = ROOT / "output" / "smile"
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"]
LCOL = {"None": "#dcdbd5", "Mild": "#eda07a", "Moderate": "#dd7646", "Severe": "#bb5228", "Extreme": "#7f2f14",
        "Ran out": "#2b2a27"}
LLAB = {"None": "None (<5%)", "Mild": "Mild (5–15%)", "Moderate": "Moderate (15–30%)", "Severe": "Severe (30–50%)",
        "Extreme": "Extreme (≥50%)", "Ran out": "Ran out of money"}
TOL = 0.02  # a decade-to-decade rise below 2% still counts as a smile in the robustness check

# label -> key in chosen_params.json
SHOW = [
    ("Bengen 4%", "Bengen 4% (50/50 US)"),
    ("Previous 8% plan", "Previous 8% plan"),
    ("Ratchet (no smile)", "Ratchet (30% intl)"),
    ("Smile, fixed spending", "Smile, fixed spending"),
    ("Smile, tiny cuts ≤5%, big raises", "Smile + tiny adjustments + cash (cuts <=5%)"),
    ("Smile, tiny both ways ≤5%", "Smile + tiny both ways (cuts and raises <=5%)"),
]


def esc(s):
    return s.replace("$", r"\$")


def style(ax):
    ax.grid(axis="y", color=GRID_C, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID_C)
    ax.tick_params(colors=MUTED, labelsize=8.5)


def describe(p):
    d2 = p.drift if p.drift2 is None else p.drift2
    d3 = d2 if p.drift3 is None else p.drift3
    s = f"{p.rate:.1%} start · {p.stocks:.0%} stocks ({p.intl:.0%} intl)"
    if p.cut_step > 0 or p.raise_step > 0:
        s += f"\ncut {p.cut_step:.1%} / raise {p.raise_step:.0%} outside ±{p.band:.0%}"
    if p.floor > 0:
        s += f" · floor {p.floor:.0%}"
    if p.ceiling > 0:
        s += f" · cap {p.ceiling:.1f}×"
    if p.drift or d2 or d3:
        s += f"\nplan {p.drift:+.1%} / {d2:+.1%} / {d3:+.1%} a year by decade"
    if p.cash > 0:
        s += f" · {p.cash:.0%} cash bucket"
    return s


def main():
    chosen = {k: vec.Params(**v) for k, v in json.load(open(OUT / "chosen_params.json")).items()}
    meta = json.load(open(OUT / "meta.json"))
    w = np.array(meta["survival_weights"])
    df = data.load()
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    sims, mets = {}, {}
    for lab, key in SHOW:
        p = chosen[key]
        sims[lab] = vec.simulate(p, *vec.windows(df, p.intl)[1:])
        mets[lab] = vec.metrics(p, sims[lab], meta["gamma"], weights=w)
    rows = []
    for lab, key in SHOW:
        m = mets[lab]
        rows.append({"strategy": lab, "settings": describe(chosen[key]).replace("\n", " · "),
                     **{k: v for k, v in m.items() if k != "levels"}})
    pd.DataFrame(rows).to_csv(OUT / "smile_summary.csv", index=False)

    # ---- 1. pain levels, both measures, plus decade spending
    n = len(SHOW)
    fig = plt.figure(figsize=(14.5, 0.62 * n + 3.4))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.78], wspace=0.08)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    ypos = np.arange(n)[::-1]
    for ax, measure, title in ((axes[0], "plan", "Deepest cut below the plan"),
                               (axes[1], "peak", "Deepest cut from the best year so far")):
        left = np.zeros(n)
        for lv in LEVELS:
            vals = []
            for lab, key in SHOW:
                if measure == "plan":
                    vals.append(np.mean(mets[lab]["levels"] == lv) * 100)
                else:
                    R = sims[lab]["reals"]
                    cut = (1 - R / np.maximum.accumulate(R, axis=1)).max(axis=1)
                    ran = sims[lab]["depleted"]
                    lvl = np.select([ran, cut >= 0.5 - 1e-9, cut >= 0.3, cut >= 0.15, cut >= 0.05],
                                    ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")
                    vals.append(np.mean(lvl == lv) * 100)
            vals = np.array(vals)
            bars = ax.barh(ypos, vals, left=left, height=0.62, color=LCOL[lv], edgecolor="white", lw=1.5,
                           label=LLAB[lv], hatch="////" if lv == "Ran out" else None)
            for b, v, l0 in zip(bars, vals, left):
                if v >= 8:
                    ax.text(l0 + v / 2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", ha="center", va="center",
                            fontsize=8.5, color="white" if lv in ("Severe", "Extreme", "Ran out") else INK)
            left += vals
        ax.set_xlim(0, 100)
        ax.margins(x=0)
        ax.set_title(title, loc="left", fontsize=10.5, color=INK)
        ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
        ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0].axvline(90, color=INK, lw=1, ls=(0, (3, 3)))
    axes[0].set_yticks(ypos, [lab for lab, _ in SHOW], fontsize=9, color=INK)
    axes[1].set_yticks(ypos, [""] * n)
    ax = axes[2]
    ax.set_xlim(0, 1)
    ax.set_ylim(axes[0].get_ylim())
    ax.axis("off")
    cols = [(0.02, "Score"), (0.2, "Start"), (0.38, "Yrs\n1–10"), (0.56, "Yrs\n11–20"), (0.74, "Yrs\n21–30"),
            (0.9, "Smile?")]
    for x, h in cols:
        ax.text(x, n - 0.35, h, fontsize=8.5, color=MUTED, va="bottom")
    for y_, (lab, key) in zip(ypos, SHOW):
        m, p = mets[lab], chosen[key]
        smile = m["typical_11_20"] <= m["typical_1_10"] * 1.001 and m["typical_21_30"] <= m["typical_11_20"] * 1.001
        flat = abs(m["typical_21_30"] / m["typical_1_10"] - 1) < 0.01
        vals = [f"${m['ce']:.2f}", f"{p.rate:.1%}", f"${m['typical_1_10']:.2f}", f"${m['typical_11_20']:.2f}",
                f"${m['typical_21_30']:.2f}", "flat" if flat else ("yes" if smile else "no")]
        for (x, _), v in zip(cols, vals):
            ax.text(x, y_, esc(v), va="center", fontsize=9.5, color=INK, fontweight="bold" if x == 0.02 else "normal")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, frameon=False, fontsize=8.5, bbox_to_anchor=(0.45, 0.0))
    fig.suptitle("Smile plans front-load spending with few deep cuts below plan, but most retirees later give back raises",
                 x=0.02, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.02, 0.925, esc("Score = certainty-equivalent spending (risk aversion 3), each year weighted by the "
                              "chance a 65-year-old couple is alive. Typical = median retiree, real $ per $100 of "
                              "starting portfolio. Dashed line: 10% extreme limit."), fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.17, right=0.99, top=0.82, bottom=0.15)
    fig.savefig(OUT / "smile_pain.png", dpi=150)
    plt.close(fig)

    # ---- 2. spending paths
    paths = SHOW[1:]
    fig, axes = plt.subplots(1, len(paths), figsize=(3.2 * len(paths) + 1, 4.9), sharey=True)
    yrs = np.arange(1, 31)
    top = 0
    for ax, (lab, key) in zip(axes, paths):
        p = chosen[key]
        R = sims[lab]["reals"] * 100
        lo, med, hi = np.percentile(R, 10, axis=0), np.median(R, axis=0), np.percentile(R, 90, axis=0)
        worst = R[np.argmin((R * w).sum(axis=1))]
        top = max(top, hi.max())
        ax.fill_between(yrs, lo, hi, color="#86b6ef", alpha=0.45, lw=0, label="10th–90th percentile")
        ax.plot(yrs, p.plan(30) * 100, color=MUTED, lw=1.2, ls=(0, (2, 2)), label="Plan (smile)")
        ax.plot(yrs, med, color="#2a78d6", lw=2.2, label="Median retiree")
        ax.plot(yrs, worst, color="#7f2f14", lw=1.4, ls=(0, (5, 2)), label="Unluckiest retiree")
        ax.set_title(lab, loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Year of retirement", color=MUTED, fontsize=9)
        ax.text(0.0, -0.2, esc(describe(p)), transform=ax.transAxes, fontsize=7, color=MUTED, va="top")
        style(ax)
    axes[0].set_ylim(0, np.ceil(top / 2) * 2 + 1)
    axes[0].set_ylabel(esc("Real spending per $100 start ($)"), color=MUTED, fontsize=9)
    axes[0].legend(frameon=False, fontsize=7.5, loc="upper right")
    fig.suptitle("Where the money goes over 30 years: the smile plans hold spending early and taper late",
                 x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.94))
    fig.savefig(OUT / "smile_paths.png", dpi=150)
    plt.close(fig)

    # ---- 3. robustness
    ev_w = w
    rng = np.random.default_rng(3)
    so.RANGES.update({"intl": (0.0, 0.30), "drift": (-0.03, 0.0), "drift2": (-0.03, 0.0), "drift3": (-0.03, 0.0)})
    names_all = ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "floor", "ceiling", "drift", "drift2",
                 "drift3"]
    fams = [("Smile, tiny cuts ≤5%, big raises", "Smile + tiny adjustments + cash (cuts <=5%)",
             {"cut_step": (0.002, 0.05)}),
            ("Smile, tiny both ways ≤5%", "Smile + tiny both ways (cuts and raises <=5%)",
             {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.05)})]
    base_ranges = dict(so.RANGES)
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axes[0]
    for i, (lab, key, ov) in enumerate(fams):
        so.RANGES.clear(); so.RANGES.update(base_ranges); so.RANGES.update(ov)
        d = {k: v for k, v in chosen[key].as_dict().items() if k in names_all}
        d = {k: (v if v is not None else 0.0) for k, v in d.items()}
        ces, ok = [], []
        for _ in range(400):
            p = so.make(so.nudge(d, names_all, rng, 0.05))
            m = vec.metrics(p, vec.simulate(p, *vec.windows(df, p.intl)[1:]), meta["gamma"], weights=ev_w)
            sm = m["typical_11_20"] <= m["typical_1_10"] * (1 + TOL) and m["typical_21_30"] <= m["typical_11_20"] * (1 + TOL)
            ces.append(m["ce"])
            ok.append(m["extreme_share"] <= meta["max_extreme"] + 1e-12 and sm)
        ces, ok = np.array(ces), np.array(ok)
        x = i + rng.uniform(-0.2, 0.2, len(ces))
        ax.scatter(x[ok], ces[ok], s=7, color="#2a78d6", alpha=0.5, lw=0)
        ax.scatter(x[~ok], ces[~ok], s=7, color="#bb5228", alpha=0.6, lw=0)
        ax.scatter([i], [mets[lab]["ce"]], s=60, marker="D", color=INK, zorder=3)
        ax.text(i, ax.get_ylim()[0], "", fontsize=1)
        fams[i] = (lab + f"\n{ok.mean():.0%} within both limits", key, ov)
    so.RANGES.clear(); so.RANGES.update(base_ranges)
    ax.axhline(mets["Previous 8% plan"]["ce"], color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(1.45, mets["Previous 8% plan"]["ce"] + 0.04, "previous 8% plan", fontsize=8, color=MUTED, va="bottom",
            ha="right")
    ax.set_xticks([0, 1], [f[0] for f in fams], fontsize=8.5)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("Score (\\$ per \\$100)", color=MUTED, fontsize=9)
    ax.set_title("Settings nudged at random (±5% of each range, 400 tries)\n◆ optimum · blue keeps both limits "
                 "(≤10% extreme, smile within 2%) · orange breaks one", loc="left", fontsize=9.5, color=INK)
    style(ax)

    ax = axes[1]
    fam_key = "Smile + tiny adjustments (cuts <=5%)"
    runs = [("", "Main: couple, risk aversion 3"), ("single", "Single person"), ("gamma2", "Risk aversion 2"),
            ("gamma5", "Risk aversion 5"), ("intl_stress", "Pessimistic intl data"), ("us_only", "US stocks only")]
    rows = []
    for d_, lab in runs:
        path = OUT / d_ if d_ else OUT
        r = pd.read_csv(path / "smile_results.csv")
        r = r[r.family == fam_key].iloc[0]
        p = vec.Params(**json.load(open(path / "chosen_params.json"))[fam_key])
        rows.append((lab, r, p))
    y = np.arange(len(rows))[::-1]
    for yy, (lab, r, p) in zip(y, rows):
        ax.plot([1, 2, 3], [r.typical_1_10, r.typical_11_20, r.typical_21_30], color="#2a78d6" if yy == y[0] else
                "#86b6ef", lw=2 if yy == y[0] else 1.4, marker="o", ms=4)
    # spread end labels so they never overlap (minimum gap in data units)
    order_ = sorted(range(len(rows)), key=lambda i: rows[i][1].typical_21_30)
    ys, gap = [], 0.09
    for i in order_:
        y0 = rows[i][1].typical_21_30
        ys.append(max(y0, ys[-1] + gap) if ys else y0)
    for i, yl in zip(order_, ys):
        lab, r, p = rows[i]
        ax.annotate(esc(f"{lab}: {p.rate:.1%} start"), (3, r.typical_21_30), xytext=(3.12, yl),
                    textcoords="data", fontsize=7.5, color=INK, va="center",
                    arrowprops=dict(arrowstyle="-", color=GRID_C, lw=0.8))
    ax.set_xticks([1, 2, 3], ["Years 1–10", "Years 11–20", "Years 21–30"])
    ax.set_xlim(0.8, 4.6)
    ax.set_ylabel("Typical spending (\\$ per \\$100)", color=MUTED, fontsize=9)
    ax.set_title("Re-optimised under other assumptions (cuts ≤5%): every version front-loads", loc="left",
                 fontsize=9.5, color=INK)
    style(ax)
    fig.suptitle("How robust is the smile optimum?", x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "smile_robustness.png", dpi=150)
    plt.close(fig)

    for lab, key in SHOW:
        m = mets[lab]
        R = sims[lab]["reals"]
        peak30 = np.mean(((1 - R / np.maximum.accumulate(R, axis=1)).max(axis=1) >= 0.3) | sims[lab]["depleted"])
        print(f"{lab:34s} score ${m['ce']:.2f} | ext {m['extreme_share']:.0%} sev+ {m['severe_plus_share']:.0%} "
              f"| from-best≥30% {peak30:.0%} | yrs ${m['typical_1_10']:.2f}/${m['typical_11_20']:.2f}/"
              f"${m['typical_21_30']:.2f} | worst ${m['worst_year']:.2f} | p10 ${m['p10_year']:.2f} | end ${m['median_final']:.0f}"
              f" | ran out {m['ran_out']}")


if __name__ == "__main__":
    main()
