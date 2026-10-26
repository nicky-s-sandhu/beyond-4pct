"""How painful is each strategy to live with? Spending cuts by severity.

For every historical 30-year retiree (1928-1996 starts) and each strategy, two
measures of the deepest cut in real spending:

  vs plan       1 - spending / planned spending. The plan is year-1 spending,
                trimmed by the strategy's drift (e.g. -0.5%/yr), so a planned
                trim is not counted as a cut.
  vs best year  1 - spending / highest spending so far (peak to trough):
                giving back earlier raises counts as a cut.

Each retiree is placed in one severity level by the deepest cut:
  None < 5% | Mild 5-15% | Moderate 15-30% | Severe 30-50% | Extreme >= 50%
  | Ran out (money exhausted before year 30).
Shares are frequencies over 69 overlapping historical windows, not forecasts.

    python scripts/pain_analysis.py
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

OUT = ROOT / "output" / "pain"
HORIZON, FLOOR = 30, 4.0

# (label, start rate, stocks, intl share, step, cap, drift); step None = Bengen constant real
STRATEGIES = [
    ("Bengen 4.0%: constant real, 50/50 US", 0.040, 0.5, 0.0, None, None, 0.0),
    ("Bengen 5.0%: constant real, 50/50 US", 0.050, 0.5, 0.0, None, None, 0.0),
    ("Guardrails ±30%, $4 floor, 80% US stocks: 5.5%", 0.055, 0.8, 0.0, 0.30, 2.0, 0.0),
    ("+ real spending −0.5%/yr: 6.3%", 0.063, 0.8, 0.0, 0.30, 2.0, -0.005),
    ("+ 25% international: 8.0%", 0.080, 0.8, 0.25, 0.30, 2.0, -0.005),
    ("Same with ±25% steps: 8.0%", 0.080, 0.8, 0.25, 0.25, 2.0, -0.005),
    ("95% success plan: 9.0%", 0.090, 0.8, 0.25, 0.30, 2.0, -0.005),
]
LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"]
EDGES = [0.05, 0.15, 0.30, 0.50]  # lower bounds of Mild, Moderate, Severe, Extreme
LABELS = {"None": "None (<5%)", "Mild": "Mild (5–15%)", "Moderate": "Moderate (15–30%)",
          "Severe": "Severe (30–50%)", "Extreme": "Extreme (≥50%)", "Ran out": "Ran out of money"}
# neutral for "none", validated one-hue ordinal orange ramp for severity, near-black for ran out
COLORS = {"None": "#dcdbd5", "Mild": "#eda07a", "Moderate": "#dd7646", "Severe": "#bb5228",
          "Extreme": "#7f2f14", "Ran out": "#2b2a27"}
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"


def level(cut, ran_out):
    if ran_out:
        return "Ran out"
    for name, edge in zip(["Extreme", "Severe", "Moderate", "Mild"], EDGES[::-1]):
        if cut >= edge - 1e-12:
            return name
    return "None"


def analyse(df_by_intl):
    rows = []
    for name, rate, stocks, intl, step, cap, drift in STRATEGIES:
        df = df_by_intl[intl]
        rule = (st.Guardrails(step=0.0) if step is None else
                st.Guardrails(step=step, band=0.2, floor=min(1.0, FLOOR / 100 / rate), ceiling=cap, drift=drift,
                              floor_follows_drift=True))
        for y in range(df.index.min(), df.index.max() - HORIZON + 2):
            p = st.simulate_path(df, y, rate, rule, stocks, HORIZON, "end")
            real = p.real_spend.values * 100
            plan = rate * 100 * (1 + drift) ** np.arange(len(real))
            vs_plan = 1 - real / plan
            peak = np.maximum.accumulate(real)
            vs_peak = 1 - real / peak
            ran_out = bool(p.shortfall.any())
            rows.append({
                "strategy": name, "start_year": y, "start_rate": rate, "ran_out": ran_out,
                "cut_vs_plan": max(0.0, vs_plan.max()), "cut_vs_peak": vs_peak.max(),
                "years_15_below_plan": int((vs_plan >= 0.15).sum()),
                "years_30_below_plan": int((vs_plan >= 0.30).sum()),
                "worst_year_spend": real.min(), "avg_spend_1_10": real[:10].mean(), "avg_spend": real.mean(),
            })
    res = pd.DataFrame(rows)
    res["level_vs_plan"] = [level(c, r) for c, r in zip(res.cut_vs_plan, res.ran_out)]
    res["level_vs_peak"] = [level(c, r) for c, r in zip(res.cut_vs_peak, res.ran_out)]
    return res


def shares(res, col):
    t = pd.crosstab(res.strategy, res[col], normalize="index").reindex(columns=LEVELS, fill_value=0.0)
    return t.reindex([s[0] for s in STRATEGIES])


def chart(res, sp, sk, path):
    names = [s[0] for s in STRATEGIES]
    n = len(names)
    fig = plt.figure(figsize=(13, 0.62 * n + 3.4))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.42], wspace=0.1)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])]
    ypos = np.arange(n)[::-1]
    for ax, tab, title in ((axes[0], sp, "Deepest cut below the plan"),
                           (axes[1], sk, "Deepest cut from the best year so far")):
        left = np.zeros(n)
        for lv in LEVELS:
            w = tab[lv].values * 100
            bars = ax.barh(ypos, w, left=left, height=0.62, color=COLORS[lv], edgecolor="white", lw=1.5,
                           label=LABELS[lv], hatch="////" if lv == "Ran out" else None)
            for b, v, l0 in zip(bars, w, left):
                if v >= 7:
                    dark = lv in ("Severe", "Extreme", "Ran out")
                    ax.text(l0 + v / 2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", ha="center", va="center",
                            fontsize=8.5, color="white" if dark else INK,
                            bbox=dict(boxstyle="round,pad=0.1", fc=COLORS[lv], ec="none") if lv == "Ran out" else None)
            left += w
        ax.set_xlim(0, 100)
        ax.set_title(title, loc="left", fontsize=10.5, color=INK)
        ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
        ax.margins(x=0)
        ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
    axes[0].set_yticks(ypos, names, fontsize=9, color=INK)
    axes[1].set_yticks(ypos, [""] * n)
    axes[0].set_xlabel("Share of 69 historical retirees", color=MUTED, fontsize=9)
    axes[1].set_xlabel("Share of 69 historical retirees", color=MUTED, fontsize=9)

    # right column: what the retiree gets
    ax = axes[2]
    ax.set_xlim(0, 1)
    ax.set_ylim(axes[0].get_ylim())
    ax.axis("off")
    g = res.groupby("strategy")
    ax.text(0.02, n - 0.35, "Typical\nyrs 1–10", fontsize=8.5, color=MUTED, va="bottom", ha="left")
    ax.text(0.52, n - 0.35, "Worst\nsingle year", fontsize=8.5, color=MUTED, va="bottom", ha="left")
    for y_, nm in zip(ypos, names):
        r = g.get_group(nm)
        ax.text(0.02, y_, f"${r.avg_spend_1_10.median():.2f}", va="center", fontsize=9.5, color=INK)
        ax.text(0.52, y_, f"${r.worst_year_spend.min():.2f}", va="center", fontsize=9.5, color=INK)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, frameon=False, fontsize=8.5,
               bbox_to_anchor=(0.45, 0.0), handlelength=1.4)
    fig.suptitle("Higher starting rates buy more spending with deeper cuts: how often each level of cut happened",
                 x=0.02, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.02, 0.935, "Real spending, 69 thirty-year retirements starting 1928–1996. Left: deepest cut below the "
             "planned path (planned 0.5%/yr trims are not cuts). Middle: deepest drop from the highest spending so far.",
             fontsize=8.5, color=MUTED)
    fig.text(0.02, 0.905, "Right: \\$ per \\$100 of starting portfolio. On the 8% plans the \\$4 floor is exactly "
             "50% below plan, so Extreme there means the retiree hit the floor.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.25, right=0.99, top=0.82, bottom=0.14)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = data.load()
    base = base.assign(bonds=0.5 * base.bills + 0.5 * base.bonds)
    df_by_intl = {i: data.with_intl(base, i) for i in {s[3] for s in STRATEGIES}}
    res = analyse(df_by_intl)
    res.to_csv(OUT / "pain_by_retiree.csv", index=False)
    sp, sk = shares(res, "level_vs_plan"), shares(res, "level_vs_peak")
    chart(res, sp, sk, OUT / "pain_levels.png")

    g = res.groupby("strategy", sort=False)
    summ = pd.DataFrame({
        "start": g.start_rate.first(),
        "typical_yrs_1_10": g.avg_spend_1_10.median(),
        "worst_year": g.worst_year_spend.min(),
        "p_cut_30_plus_vs_plan": g.apply(lambda d: ((d.cut_vs_plan >= 0.30) | d.ran_out).mean(), include_groups=False),
        "p_cut_30_plus_vs_peak": g.apply(lambda d: ((d.cut_vs_peak >= 0.30) | d.ran_out).mean(), include_groups=False),
        "median_yrs_15_below_plan": g.years_15_below_plan.median(),
        "yrs_30_below_plan_if_any": g.apply(lambda d: d.loc[d.years_30_below_plan > 0, "years_30_below_plan"].median(),
                                            include_groups=False),
    })
    L = ["# Spending pain by strategy\n",
         "Share of 69 historical 30-year retirees (1928–1996 starts) whose deepest real spending cut fell in each "
         "level. Frequencies over overlapping windows, not forecasts.\n",
         "## Deepest cut below the plan\n", sp.map(lambda v: f"{v:.0%}").to_markdown(),
         "\n## Deepest cut from the best year so far\n", sk.map(lambda v: f"{v:.0%}").to_markdown(),
         "\n## Summary\n", summ.to_markdown(floatfmt=".2f")]
    (OUT / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
