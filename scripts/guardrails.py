"""Guardrails experiment: how much spending flexibility buys you.

Runs Guyton-Klinger-style guardrails over every historical 30-year retirement
for a range of `step` values (the max real change in spending per year).
step=0 is Bengen's constant-real rule.

Examples:
    python scripts/guardrails.py
    python scripts/guardrails.py --rates 0.05 --steps 0,0.05,0.1 --band 0.15
    python scripts/guardrails.py --floor 0.8 --gk
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import data, strategies as st  # noqa: E402
from reproduce import style, MUTED  # noqa: E402

OUT = ROOT / "output" / "guardrails"
PALETTE = ["#6b7280", "#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2"]


def floats(s):
    return [float(x) for x in s.split(",")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rates", type=floats, default=[0.04, 0.05], help="initial withdrawal rates")
    ap.add_argument("--steps", type=floats, default=[0, 0.05, 0.10, 0.15, 0.20, 0.25],
                    help="variance knob: max real spending change per year (0 = Bengen)")
    ap.add_argument("--band", type=float, default=0.20, help="guardrail width around the initial rate")
    ap.add_argument("--floor", type=float, default=None, help="min real spending, multiple of year-1 spending")
    ap.add_argument("--ceiling", type=float, default=None, help="max real spending, multiple of year-1 spending")
    ap.add_argument("--gk", action="store_true",
                    help="add Guyton-Klinger extras: skip inflation raise after losses; no cuts in last 15 yrs")
    ap.add_argument("--stocks", type=float, default=0.5)
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--timing", choices=["start", "end"], default="end")
    ap.add_argument("--bonds", choices=["10y", "intermediate"], default="intermediate")
    ap.add_argument("--intl", type=float, default=0.25,
                    help="share of the stock allocation in developed ex-US stocks (default 25%%)")
    ap.add_argument("--focus-year", type=int, default=1966, help="retiree to plot year by year")
    ap.add_argument("--name", default="", help="subfolder of output/guardrails/ for this run")
    a = ap.parse_args()
    global OUT
    OUT = OUT / a.name if a.name else OUT
    OUT.mkdir(parents=True, exist_ok=True)

    df = data.load()
    if a.bonds == "intermediate":
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    df = data.with_intl(df, a.intl)
    starts = range(df.index.min(), df.index.max() - a.horizon + 2)

    def rule(step):
        return st.Guardrails(step=step, band=a.band, floor=a.floor, ceiling=a.ceiling,
                             skip_inflation_after_loss=a.gk, no_cuts_last=15 if a.gk else 0)

    # ---- summary across all retirement years
    rows, detail = [], []
    for r in a.rates:
        for s in a.steps:
            m = st.run_all(df, starts, r, rule(s), a.stocks, a.horizon, a.timing)
            m["rate"], m["step"] = r, s
            detail.append(m)
            rows.append({
                "rate": r, "step": s,
                "failures": int(m.depleted.sum()),
                "worst_min_spend": m.min_real_spend.min(),
                "median_avg_spend": m.avg_real_spend.median(),
                "worst_avg_spend": m.avg_real_spend.min(),
                "worst_cut_1yr": m.max_yearly_cut.max(),
                "median_vol": m.yearly_vol.median(),
                "worst_yrs_below_90": int(m.years_below_90pct.max()),
                "median_final_bal": m.final_real_balance.median(),
            })
    summ = pd.DataFrame(rows)
    pd.concat(detail).to_csv(OUT / "guardrails_by_start_year.csv", index=False)
    summ.to_csv(OUT / "guardrails_summary.csv", index=False)

    # ---- markdown report
    L = [f"# Guardrails experiment\n",
         f"{len(starts)} retirements ({starts[0]}–{starts[-1]}), {a.horizon} yrs, {a.stocks:.0%} stocks, "
         f"band ±{a.band:.0%}, stocks {1 - a.intl:.0%} US / {a.intl:.0%} intl, withdrawals at year {a.timing}"
         + (f", floor {a.floor:.0%}" if a.floor else "") + (f", ceiling {a.ceiling:.0%}" if a.ceiling else "")
         + (", GK extras on" if a.gk else "") + ".\n",
         "Spending is in real dollars per $100 of starting portfolio. "
         "`step` = largest real change in spending in any one year (0 = Bengen).\n",
         "| Rate | Step | Failures | Worst min spend | Median avg spend | Worst avg spend "
         "| Worst 1-yr cut | Median yearly vol | Worst yrs <90% | Median final bal |",
         "|---" * 10 + "|"]
    for _, x in summ.iterrows():
        L.append(f"| {x.rate:.1%} | {x.step:.0%} | {int(x.failures)} | ${x.worst_min_spend:.2f} | ${x.median_avg_spend:.2f} "
                 f"| ${x.worst_avg_spend:.2f} | {x.worst_cut_1yr:.0%} | {x.median_vol:.1%} | {int(x.worst_yrs_below_90)} "
                 f"| ${x.median_final_bal:.0f} |")
    (OUT / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))

    # ---- fig: one retiree's real spending path per step
    r0 = max(a.rates)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for i, s in enumerate(a.steps):
        p = st.simulate_path(df, a.focus_year, r0, rule(s), a.stocks, a.horizon, a.timing)
        ax.plot(p.year, p.real_spend * 100, color=PALETTE[i % len(PALETTE)], lw=2 if s == 0 else 1.6,
                ls="--" if s == 0 else "-", label="Bengen (0%)" if s == 0 else f"±{s:.0%}")
    ax.axhline(r0 * 100, color=MUTED, lw=0.8, ls=":")
    style(ax, f"Real spending for a {a.focus_year} retiree starting at {r0:.1%}", "Real \\$ per \\$100 start")
    ax.legend(title="Step", frameon=False, ncol=len(a.steps), loc="upper center", bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout(); fig.savefig(OUT / f"spending_path_{a.focus_year}.png", dpi=150); plt.close(fig)

    # ---- fig: the trade-off (worst-case floor vs typical spending) as step grows
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for i, r in enumerate(a.rates):
        s = summ[summ.rate == r]
        c = PALETTE[1 + i]
        axes[0].plot(s.step * 100, s.worst_min_spend, marker="o", color=c, label=f"{r:.1%} start")
        axes[1].plot(s.step * 100, s.median_avg_spend, marker="o", color=c, label=f"{r:.1%} start")
    style(axes[0], "Worst-case lowest year of spending", "Real \\$ per \\$100 start")
    style(axes[1], "Typical (median) average spending", "Real \\$ per \\$100 start")
    for ax in axes:
        ax.set_xlabel("Step: max real change per year (%)", color=MUTED)
        ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "tradeoff.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
