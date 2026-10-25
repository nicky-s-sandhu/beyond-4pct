"""Reproduce the core results of Bengen (1994) and extend them to today.

Usage:
    python scripts/reproduce.py              # use data/raw snapshot (or downloaded files if present)
    python scripts/reproduce.py --download   # fetch fresh data from Damodaran + FRED first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, simulate as sim  # noqa: E402

OUT = ROOT / "output"
RATES = [0.03, 0.04, 0.05, 0.06]
SHARES = [0.0, 0.25, 0.50, 0.75, 1.0]
INK, MUTED, GRID = "#1f2328", "#6b7280", "#e5e7eb"
COLORS = {0.03: "#2563eb", 0.04: "#16a34a", 0.05: "#d97706", 0.06: "#dc2626"}


def style(ax, title, ylabel):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--timing", choices=["start", "end"], default="end",
                    help="withdraw at start or end of each year (default: end)")
    ap.add_argument("--bonds", choices=["10y", "intermediate"], default="intermediate",
                    help="10y = 10-yr Treasury; intermediate = 50/50 bills + 10-yr, a ~5-yr duration proxy "
                         "for Bengen's Ibbotson intermediate-term government bonds")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    df = data.download() if a.download else data.load()
    if a.bonds == "intermediate":
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    b94 = sim.bengen1994_series(df, last_actual=1992)
    starts94 = range(df.index.min(), 1977)  # Bengen's retirees: through 1976
    lines = [f"# Bengen (1994) replication\n",
             f"Data: {df.index.min()}–{df.index.max()} · withdrawals at year {a.timing} · "
             f"bonds = {'10-yr Treasury' if a.bonds == '10y' else 'intermediate proxy (½ bills + ½ 10-yr)'} · annual rebalancing\n",
             f"Post-1992 assumption (Bengen mode): stocks {b94.loc[1993,'stocks']:.1%}, "
             f"bonds {b94.loc[1993,'bonds']:.1%}, inflation {b94.loc[1993,'inflation']:.1%} per year\n"]

    # ---- Fig 1: longevity by start year, 50/50, Bengen mode (cap 50 yrs)
    t = sim.longevity_table(b94, starts94, RATES, 0.5, 50, a.timing)
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for r in RATES:
        s = t[t.rate == r]
        ax.plot(s.start_year, s.years, marker="o", ms=3, lw=1.6, color=COLORS[r], label=f"{r:.0%}")
    ax.axhline(30, color=MUTED, ls="--", lw=1)
    ax.text(starts94[-1] + 0.5, 30.5, "30 yrs", color=MUTED, fontsize=9)
    style(ax, "Years a 50/50 portfolio lasts, by retirement year (capped at 50)", "Years")
    ax.legend(title="Initial rate", frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout(); fig.savefig(OUT / "fig1_longevity_by_start_year.png", dpi=150); plt.close(fig)

    lines.append("\n## 1. Minimum longevity across retirement years (50/50, Bengen mode)\n")
    lines.append("| Initial rate | Worst case (years) | Worst start year | Share lasting ≥30 yrs |")
    lines.append("|---|---|---|---|")
    for r in RATES:
        s = t[t.rate == r]
        w = s.loc[s.years.idxmin()]
        lines.append(f"| {r:.0%} | {w.years:.1f} | {int(w.start_year)} | {(s.years >= 30).mean():.0%} |")

    # ---- Fig 2 / table: allocation
    lines.append("\n## 2. Minimum longevity by stock allocation (Bengen mode)\n")
    lines.append("| Rate \\ Stocks | " + " | ".join(f"{x:.0%}" for x in SHARES) + " |")
    lines.append("|---" * (len(SHARES) + 1) + "|")
    alloc = {}
    for r in RATES:
        mins = [sim.longevity_table(b94, starts94, [r], sh, 50, a.timing).years.min() for sh in SHARES]
        alloc[r] = mins
        lines.append(f"| {r:.0%} | " + " | ".join(f"{m:.1f}" for m in mins) + " |")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for r in RATES:
        ax.plot([s * 100 for s in SHARES], alloc[r], marker="o", color=COLORS[r], lw=1.8, label=f"{r:.0%}")
    ax.axhline(30, color=MUTED, ls="--", lw=1)
    style(ax, "Worst-case longevity vs. stock allocation", "Years (worst start year)")
    ax.set_xlabel("Stocks in portfolio (%)", color=MUTED)
    ax.legend(title="Initial rate", frameon=False, ncol=4)
    fig.tight_layout(); fig.savefig(OUT / "fig2_allocation.png", dpi=150); plt.close(fig)

    # ---- Fig 3: 30-yr SAFEMAX by start year, Bengen mode vs actual history
    last_full = df.index.max() - 29
    rows = []
    for y in range(df.index.min(), max(1977, last_full) + 1):
        rows.append({"start_year": y,
                     "bengen_mode": sim.safemax(b94, y, 30, 0.5, a.timing) if y <= 1976 else np.nan,
                     "actual": sim.safemax(df, y, 30, 0.5, a.timing)})
    sm = pd.DataFrame(rows).astype(float)
    sm.to_csv(OUT / "safemax_30yr_50_50.csv", index=False)
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(sm.start_year, sm.actual * 100, color="#2563eb", lw=1.8, marker="o", ms=3, label="Actual returns")
    ax.plot(sm.start_year, sm.bengen_mode * 100, color="#d97706", lw=1.2, ls="--", label="Bengen mode (avg after 1992)")
    ax.axhline(4, color=MUTED, ls=":", lw=1)
    style(ax, "Highest sustainable 30-year withdrawal rate, 50/50 portfolio", "Initial withdrawal rate (%)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "fig3_safemax_30yr.png", dpi=150); plt.close(fig)

    a_min = sm.loc[sm.actual.idxmin()]
    b_min = sm.loc[sm.bengen_mode.idxmin()]
    lines.append("\n## 3. 30-year SAFEMAX (50/50)\n")
    lines.append(f"- Bengen mode, retirees {starts94[0]}–1976: lowest = **{b_min.bengen_mode:.2%}** (start {int(b_min.start_year)})")
    lines.append(f"- Actual history, retirees {df.index.min()}–{last_full}: lowest = **{a_min.actual:.2%}** (start {int(a_min.start_year)})")
    lines.append(f"- Median actual SAFEMAX: {sm.actual.median():.2%}")

    # ---- full-history 4% check
    t_all = sim.longevity_table(df, range(df.index.min(), last_full + 1), [0.04], 0.5, 30, a.timing)
    fails = t_all[t_all.depleted]
    lines.append(f"\n## 4. 4% rule on actual history ({df.index.min()}–{last_full} starts, 30 yrs, 50/50)\n")
    lines.append(f"- Survived 30 years in {(~t_all.depleted).sum()} of {len(t_all)} start years"
                 + (f"; failures: {', '.join(map(str, fails.start_year))}" if len(fails) else ""))

    (OUT / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
