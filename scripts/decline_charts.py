"""Charts for declining spending with a fixed 75% floor and capped raises.
Run scripts/decline_optimize.py first (seeds merged into output/decline/best).

  decline_pain.png        cut severity (below plan; from best year) with decade spending
  decline_paths.png       real spending by year: median, 10-90% band, unluckiest retiree, plan, floor
  decline_robustness.png  random nudges of the settings; re-optimised under other assumptions

    python scripts/decline_charts.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
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

OUT = ROOT / "output" / "decline"
BEST = OUT / "best"
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"]
LCOL = {"None": "#dcdbd5", "Mild": "#eda07a", "Moderate": "#dd7646", "Severe": "#bb5228", "Extreme": "#7f2f14",
        "Ran out": "#2b2a27"}
LLAB = {"None": "None (<5%)", "Mild": "Mild (5–15%)", "Moderate": "Moderate (15–30%)", "Severe": "Severe (30–50%)",
        "Extreme": "Extreme (≥50%)", "Ran out": "Ran out of money"}
SHOW = [("Bengen 4%", "Bengen 4% (50/50 US)"), ("Previous 8% plan", "Previous 8% plan"),
        ("Raises ≤5%", "Cuts <=5%, raises <=5%"), ("Raises ≤10%", "Cuts <=5%, raises <=10%"),
        ("Raises ≤15%", "Cuts <=5%, raises <=15%"), ("Raises ≤10%, any cut size", "Any cuts, raises <=10%")]
NAMES = ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "ceiling", "drift"]
TOL = 0.02


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
    s = f"{p.rate:.1%} start · {p.stocks:.0%} stocks ({p.intl:.0%} intl)"
    if p.cut_step or p.raise_step:
        s += f"\ncut {p.cut_step:.1%} / raise {p.raise_step:.1%} outside ±{p.band:.1%}"
    if p.floor:
        s += f"\nfloor {p.floor:.0%} of year 1" if p.floor_flat else f"\nfloor {p.floor:.0%} of plan"
    if p.ceiling:
        s += f" · cap {p.ceiling:.1f}×"
    if p.drift:
        s += f" · plan {p.drift:+.1%}/yr"
    return s


def levels(cut, ran):
    return np.select([ran, cut >= 0.5 - 1e-9, cut >= 0.3, cut >= 0.15, cut >= 0.05],
                     ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")


def merge_best(runs=("", "seed22", "seed23")):
    """Keep the highest-scoring result per family across seed runs in output/decline/best."""
    best = {}
    for d in runs:
        path = OUT / d if d else OUT
        if not (path / "decline_results.csv").exists():
            continue
        r = pd.read_csv(path / "decline_results.csv")
        c = json.load(open(path / "chosen_params.json"))
        for _, x in r.iterrows():
            if x.family not in best or (x.kind == "optimised" and x.ce > best[x.family][0]):
                best[x.family] = (x.ce, c[x.family], d or "seed21")
    BEST.mkdir(parents=True, exist_ok=True)
    json.dump({k: v[1] for k, v in best.items()}, open(BEST / "chosen_params.json", "w"), indent=2)
    json.dump({k: v[2] for k, v in best.items()}, open(BEST / "source_runs.json", "w"), indent=2)
    (BEST / "meta.json").write_text((OUT / "meta.json").read_text())


def main():
    merge_best()
    chosen = {k: vec.Params(**v) for k, v in json.load(open(BEST / "chosen_params.json")).items()}
    meta = json.load(open(BEST / "meta.json"))
    w = np.array(meta["survival_weights"])
    df = data.load()
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    sims, mets = {}, {}
    for lab, key in SHOW:
        p = chosen[key]
        sims[lab] = vec.simulate(p, *vec.windows(df, p.intl)[1:])
        mets[lab] = vec.metrics(p, sims[lab], meta["gamma"], weights=w)

    summary = []
    for lab, key in SHOW:
        m, R, ran = mets[lab], sims[lab]["reals"], sims[lab]["depleted"]
        peak_cut = (1 - R / np.maximum.accumulate(R, axis=1)).max(axis=1)
        first_cut = (1 - R / R[:, :1]).max(axis=1)
        summary.append({"strategy": lab, "settings": describe(chosen[key]).replace("\n", " · "), "score": m["ce"],
                        "start": chosen[key].rate, "yrs_1_10": m["typical_1_10"], "yrs_11_20": m["typical_11_20"],
                        "yrs_21_30": m["typical_21_30"], "extreme_or_ran_out": m["extreme_share"],
                        "ran_out": m["ran_out"], "cut_30_from_best": float(np.mean((peak_cut >= 0.3) | ran)),
                        "below_first_year_25_plus": float(np.mean((first_cut >= 0.25 - 1e-9) | ran)),
                        "worst_year": m["worst_year"], "median_end_balance": m["median_final"]})
    summ = pd.DataFrame(summary)
    summ.to_csv(BEST / "decline_summary.csv", index=False)

    # ---- 1. pain
    n = len(SHOW)
    fig = plt.figure(figsize=(14.5, 0.62 * n + 3.4))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.72], wspace=0.08)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    ypos = np.arange(n)[::-1]
    for ax, measure, title in ((axes[0], "plan", "Deepest cut below the plan"),
                               (axes[1], "peak", "Deepest cut from the best year so far")):
        left = np.zeros(n)
        for lv in LEVELS:
            vals = []
            for lab, key in SHOW:
                R, ran = sims[lab]["reals"], sims[lab]["depleted"]
                if measure == "plan":
                    lv_arr = mets[lab]["levels"]
                else:
                    lv_arr = levels((1 - R / np.maximum.accumulate(R, axis=1)).max(axis=1), ran)
                vals.append(np.mean(lv_arr == lv) * 100)
            vals = np.array(vals)
            bars = ax.barh(ypos, vals, left=left, height=0.62, color=LCOL[lv], edgecolor="white", lw=1.5,
                           label=LLAB[lv], hatch="////" if lv == "Ran out" else None)
            for b, v, l0 in zip(bars, vals, left):
                if v >= 8:
                    ax.text(l0 + v / 2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", ha="center", va="center",
                            fontsize=8.5, color="white" if lv in ("Severe", "Extreme", "Ran out") else INK)
            left += vals
        ax.set_xlim(0, 100)
        ax.set_title(title, loc="left", fontsize=10.5, color=INK)
        ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
        ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0].axvline(90, color=INK, lw=1, ls=(0, (3, 3)))
    axes[0].set_yticks(ypos, [lab for lab, _ in SHOW], fontsize=9, color=INK)
    axes[1].set_yticks(ypos, [""] * n)
    ax = axes[2]
    ax.set_xlim(0, 1); ax.set_ylim(axes[0].get_ylim()); ax.axis("off")
    cols = [(0.0, "Score"), (0.19, "Start"), (0.37, "Yrs\n1–10"), (0.55, "Yrs\n11–20"), (0.73, "Yrs\n21–30"),
            (0.9, "Ran\nout")]
    for x, h in cols:
        ax.text(x, n - 0.35, h, fontsize=8.5, color=MUTED, va="bottom")
    for y_, (lab, key) in zip(ypos, SHOW):
        m = mets[lab]
        vals = [f"${m['ce']:.2f}", f"{chosen[key].rate:.1%}", f"${m['typical_1_10']:.2f}",
                f"${m['typical_11_20']:.2f}", f"${m['typical_21_30']:.2f}", f"{m['ran_out']}"]
        for (x, _), v in zip(cols, vals):
            ax.text(x, y_, esc(v), va="center", fontsize=9.5, color=INK, fontweight="bold" if x == 0 else "normal")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, frameon=False, fontsize=8.5, bbox_to_anchor=(0.45, 0.0))
    fig.suptitle("Declining spending with a 75% floor: small cuts, few deep cuts below plan; bigger raises cost "
                 "more give-backs", x=0.02, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.02, 0.925, esc("Score = certainty-equivalent spending (risk aversion 3), years weighted by a 65-year-old "
                              "couple's survival. Typical = median retiree, real $ per $100 of starting portfolio. "
                              "Cuts ≤5% a year except the last row."), fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.15, right=0.99, top=0.82, bottom=0.15)
    fig.savefig(BEST / "decline_pain.png", dpi=150)
    plt.close(fig)

    # ---- 2. paths
    paths = [s for s in SHOW if s[0] in ("Previous 8% plan", "Raises ≤5%", "Raises ≤10%", "Raises ≤15%")]
    fig, axes = plt.subplots(1, len(paths), figsize=(3.4 * len(paths) + 1, 4.9), sharey=True)
    yrs = np.arange(1, 31)
    top = 0
    for ax, (lab, key) in zip(axes, paths):
        p = chosen[key]
        R = sims[lab]["reals"] * 100
        lo, med, hi = np.percentile(R, 10, axis=0), np.median(R, axis=0), np.percentile(R, 90, axis=0)
        worst = R[np.argmin((R * w).sum(axis=1))]
        top = max(top, hi.max())
        ax.fill_between(yrs, lo, hi, color="#86b6ef", alpha=0.45, lw=0, label="10th–90th percentile")
        ax.plot(yrs, p.plan(30) * 100, color=MUTED, lw=1.2, ls=(0, (2, 2)), label="Plan")
        if p.floor and p.floor_flat:
            ax.axhline(p.floor * p.rate * 100, color=INK, lw=0.9, ls=":", label="Floor (75% of year 1)")
        ax.plot(yrs, med, color="#2a78d6", lw=2.2, label="Median retiree")
        ax.plot(yrs, worst, color="#7f2f14", lw=1.4, ls=(0, (5, 2)), label="Unluckiest retiree")
        ax.set_title(lab if lab == "Previous 8% plan" else f"Declining, cuts ≤5%, {lab.lower()}", loc="left",
                     fontsize=10, color=INK)
        ax.set_xlabel("Year of retirement", color=MUTED, fontsize=9)
        ax.text(0.0, -0.2, esc(describe(p)), transform=ax.transAxes, fontsize=7, color=MUTED, va="top")
        style(ax)
    axes[0].set_ylim(0, np.ceil(top / 2) * 2 + 1)
    axes[0].set_ylabel(esc("Real spending per $100 start ($)"), color=MUTED, fontsize=9)
    axes[-1].legend(frameon=False, fontsize=7.5, loc="upper right")
    fig.suptitle("Spending over 30 years: the floor holds the unlucky at 75% of year 1; raises lift the median",
                 x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.94))
    fig.savefig(BEST / "decline_paths.png", dpi=150)
    plt.close(fig)

    # ---- 3. robustness
    so.RANGES.update({"intl": (0.0, meta["max_intl"]), "drift": (-0.03, 0.0)})
    base_make, base_ranges = so.make, dict(so.RANGES)
    fixed = lambda d: replace(base_make(d), floor=meta["floor"], floor_flat=True, drift2=None, drift3=None,
                              cash=0.0, bucket=False)
    rng = np.random.default_rng(5)
    fams = [("Raises ≤10%", "Cuts <=5%, raises <=10%", {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.10)}),
            ("Raises ≤15%", "Cuts <=5%, raises <=15%", {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.15)})]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8), gridspec_kw={"width_ratios": [1, 1.2]})
    ax = axes[0]
    labels = []
    for i, (lab, key, ov) in enumerate(fams):
        so.RANGES.clear(); so.RANGES.update(base_ranges); so.RANGES.update(ov)
        d = {k: chosen[key].as_dict()[k] for k in NAMES}
        ces, ok = [], []
        for _ in range(400):
            p = fixed(so.nudge(d, NAMES, rng, 0.05))
            m = vec.metrics(p, vec.simulate(p, *vec.windows(df, p.intl)[1:]), meta["gamma"], weights=w)
            t1, t2, t3 = m["typical_1_10"], m["typical_11_20"], m["typical_21_30"]
            ces.append(m["ce"])
            ok.append(m["extreme_share"] <= meta["max_extreme"] + 1e-12 and t2 <= t1 * (1 + TOL) and t3 <= t2 * (1 + TOL))
        ces, ok = np.array(ces), np.array(ok)
        x = i + rng.uniform(-0.2, 0.2, len(ces))
        ax.scatter(x[ok], ces[ok], s=7, color="#2a78d6", alpha=0.5, lw=0)
        ax.scatter(x[~ok], ces[~ok], s=7, color="#bb5228", alpha=0.6, lw=0)
        ax.scatter([i], [mets[lab]["ce"]], s=60, marker="D", color=INK, zorder=3)
        labels.append(f"{lab} (cuts ≤5%)\n{ok.mean():.0%} within both limits")
    so.RANGES.clear(); so.RANGES.update(base_ranges)
    ax.axhline(mets["Previous 8% plan"]["ce"], color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(1.5, mets["Previous 8% plan"]["ce"] + 0.03, "previous 8% plan", fontsize=8, color=MUTED, va="bottom",
            ha="right")
    ax.set_xticks([0, 1], labels, fontsize=8.5)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("Score (\\$ per \\$100)", color=MUTED, fontsize=9)
    ax.set_title("Settings nudged at random (±5% of range, 400 tries)\n◆ optimum · blue keeps both limits · "
                 "orange breaks one", loc="left", fontsize=9.5, color=INK)
    style(ax)

    ax = axes[1]
    key = "Cuts <=5%, raises <=10%"
    runs = [("", "Main: couple, risk aversion 3"), ("single", "Single person"), ("gamma2", "Risk aversion 2"),
            ("gamma5", "Risk aversion 5"), ("intl_stress", "Pessimistic intl data"), ("us_only", "US stocks only")]
    rows = []
    for d_, lab in runs:
        path = OUT / d_ if d_ else OUT
        r = pd.read_csv(path / "decline_results.csv")
        r = r[r.family == key].iloc[0]
        p = vec.Params(**json.load(open(path / "chosen_params.json"))[key])
        rows.append((lab, r, p))
    for i, (lab, r, p) in enumerate(rows):
        ax.plot([1, 2, 3], [r.typical_1_10, r.typical_11_20, r.typical_21_30],
                color="#2a78d6" if i == 0 else "#86b6ef", lw=2 if i == 0 else 1.4, marker="o", ms=4)
    order = sorted(range(len(rows)), key=lambda i: rows[i][1].typical_21_30)
    ys = []
    for i in order:
        y0 = rows[i][1].typical_21_30
        ys.append(max(y0, ys[-1] + 0.07) if ys else y0)
    for i, yl in zip(order, ys):
        lab, r, p = rows[i]
        ax.annotate(esc(f"{lab}: {p.rate:.1%} start, plan {p.drift:+.1%}/yr"), (3, r.typical_21_30), xytext=(3.12, yl),
                    fontsize=7.5, color=INK, va="center", arrowprops=dict(arrowstyle="-", color=GRID_C, lw=0.8))
    ax.set_xticks([1, 2, 3], ["Years 1–10", "Years 11–20", "Years 21–30"])
    ax.set_xlim(0.8, 4.8)
    ax.set_ylabel("Typical spending (\\$ per \\$100)", color=MUTED, fontsize=9)
    ax.set_title("Raises ≤10% re-optimised under other assumptions:\ntypical spending by decade", loc="left",
                 fontsize=9.5, color=INK)
    style(ax)
    fig.suptitle("How robust is it?", x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(BEST / "decline_robustness.png", dpi=150)
    plt.close(fig)

    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(summ.drop(columns="settings").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
