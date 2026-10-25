"""Search stock share x guardrail step x ceiling x spending drift for the best
starting rate, at a chosen historical success level.

A retiree "fails" if real spending ever drops below --target (default $4 per
$100 of starting portfolio, i.e. Bengen's 4%) or the money runs out. A spending
floor sits exactly at the target; guardrails, the ceiling and the drift shape
everything above it.

For each combination the search finds the highest starting rate (0.1% grid)
such that it, and every lower rate, keeps failures within the allowance.
Combinations are then ranked by typical (median) spending: either over the
first 10 years (--rank early, default) or over the whole 30 years (--rank avg).

Knobs searched
  --stocks    stock share; >100% = leverage borrowed at T-bills + --spread
  --steps     guardrail step = max real change in spending per year
  --ceilings  cap on real spending as a multiple of the planned path (0 = none)
  --drifts    planned real change per year, e.g. -0.005 = inflation minus 0.5%

Examples:
    python scripts/optimize.py --success 0.95 --name p95
    python scripts/optimize.py --success 1.0 --drifts 0,-0.005,-0.01
    python scripts/optimize.py --rank avg --ceilings 0,1.5,2
"""
from __future__ import annotations

import argparse
import math
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
from bengen import data, strategies as st  # noqa: E402
from reproduce import style, MUTED, INK  # noqa: E402

OUT = ROOT / "output" / "optimize"


def floats(s):
    return [float(x) for x in s.split(",")]


def esc(s):
    return s.replace("$", r"\$")


def evaluate(windows, rate, step, band, floor, ceiling, drift, timing, target, floor_drift=0.0):
    """windows: list of (returns, inflation, start_year). With floor_drift, the
    target declines along with the floor: year-k minimum = target x (1+floor_drift)^k."""
    res = [(y, *st.fast_guardrails(r, i, rate, step, band, floor, ceiling, timing, drift, 10, floor_drift))
           for r, i, y in windows]
    failed = [y for y, d, mn, *_ in res if d or mn * 100 < target - 1e-9]
    col = lambda k: [x[k] for x in res]
    return {"failures": len(failed), "failed_years": " ".join(map(str, failed)),
            "min_real": min(col(2)) * 100,
            "median_avg": float(np.median(col(3))) * 100,
            "worst_avg": min(col(3)) * 100,
            "median_early": float(np.median(col(5))) * 100,
            "worst_early": min(col(5)) * 100,
            "median_final": float(np.median(col(4))) * 100,
            "worst_final": min(col(4)) * 100}


def max_safe_rate(windows, step, band, target, ceiling, drift, timing, grid, allow, floor_drift=0.0):
    """Highest grid rate such that it and every lower rate has <= `allow` failures."""
    best = None
    for r in grid:
        floor = min(1.0, (target / 100) / r)
        m = evaluate(windows, r, step, band, floor, ceiling, drift, timing, target, floor_drift)
        if m["failures"] > allow:
            break
        best = (r, m)
    return best


def rule_for(row, a):
    fl = min(1.0, (a.target / 100) / row.max_rate)
    return st.Guardrails(step=row.step, band=a.band, floor=fl,
                         ceiling=row.ceiling if row.ceiling > 0 else None, drift=row.drift,
                         floor_follows_drift=not a.flat_floor)


def describe(row):
    c = "no cap" if row.ceiling == 0 else f"cap {row.ceiling:g}×"
    d = "flat real" if row.drift == 0 else f"{row.drift:+.1%}/yr real"
    return f"{row.stocks:.0%} stocks, ±{row.step:.0%} steps, {c}, {d}, {row.max_rate:.1%} start"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=float, default=4.0, help="min real spending per $100 start")
    ap.add_argument("--success", type=float, default=None,
                    help="required historical success rate, e.g. 0.95 (overrides --allow)")
    ap.add_argument("--allow", type=int, default=0, help="tolerate this many failed retirees")
    ap.add_argument("--stocks", type=floats, default=[0.6, 0.7, 0.8, 0.9, 1.0, 1.25])
    ap.add_argument("--steps", type=floats, default=[0, 0.10, 0.15, 0.20, 0.25, 0.30])
    ap.add_argument("--ceilings", type=floats, default=[0, 1.0, 1.25, 1.5, 2.0, 3.0],
                    help="cap as multiple of planned real spending; 0 = no cap")
    ap.add_argument("--drifts", type=floats, default=[0.0, -0.005])
    ap.add_argument("--flat-floor", action="store_true",
                    help="keep the floor flat at --target in real terms even when spending drifts down "
                         "(default: the floor declines with the drift, so year-30 minimum = target x (1+drift)^29)")
    ap.add_argument("--rank", choices=["early", "avg"], default="early",
                    help="early = median spending in years 1-10; avg = median over all years")
    ap.add_argument("--band", type=float, default=0.20)
    ap.add_argument("--spread", type=float, default=0.01, help="borrowing cost over T-bills for leverage")
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--timing", choices=["start", "end"], default="end")
    ap.add_argument("--bonds", choices=["10y", "intermediate"], default="intermediate")
    ap.add_argument("--intl", type=float, default=0.25,
                    help="share of the stock allocation in developed ex-US stocks (default 25%%)")
    ap.add_argument("--intl-stress", action="store_true",
                    help="use the pessimistic international series (wartime data gaps filled with heavy losses)")
    ap.add_argument("--name", default="", help="subfolder of output/optimize/ for this run")
    a = ap.parse_args()
    global OUT
    OUT = OUT / a.name if a.name else OUT
    OUT.mkdir(parents=True, exist_ok=True)

    df = data.load(intl_series="intl_stress" if a.intl_stress else "intl")
    if a.bonds == "intermediate":
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    df = data.with_intl(df, a.intl)
    starts = list(range(df.index.min(), df.index.max() - a.horizon + 2))
    n = len(starts)
    allow = math.floor((1 - a.success) * n + 1e-9) if a.success is not None else a.allow
    success = 1 - allow / n
    grid = np.round(np.arange(a.target / 100, 0.15001, 0.001), 4)  # below target can never qualify
    key = "median_early" if a.rank == "early" else "median_avg"

    rows = []
    for s in a.stocks:
        rets = st.portfolio_returns(df, s, a.spread)
        windows = [(list(rets.loc[y:y + a.horizon - 1]), list(df.inflation.loc[y:y + a.horizon - 1]), y)
                   for y in starts]
        for step in a.steps:
            for c in a.ceilings:
                for d in a.drifts:
                    b = max_safe_rate(windows, step, a.band, a.target, c if c > 0 else None, d,
                                      a.timing, grid, allow, 0.0 if a.flat_floor else d)
                    row = {"stocks": s, "step": step, "ceiling": c, "drift": d,
                           "max_rate": b[0] if b else np.nan}
                    row.update(b[1] if b else {})
                    rows.append(row)
        print(f"stocks {s:.0%} done", file=sys.stderr)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "optimize_grid.csv", index=False)
    ok = res.dropna(subset=["max_rate"]).sort_values(key, ascending=False)
    top = ok.iloc[0]

    # ---- heatmaps: per drift, best ceiling for each stocks x step cell
    for d in a.drifts:
        sub = ok[ok.drift == d].sort_values(key, ascending=False).drop_duplicates(["stocks", "step"])
        mat = np.full((len(a.stocks), len(a.steps)), np.nan)
        lab = {}
        for _, x in sub.iterrows():
            i, j = a.stocks.index(x.stocks), a.steps.index(x.step)
            mat[i, j] = x[key]
            lab[(i, j)] = f"${x[key]:.1f}\n{x.max_rate:.1%} · " + ("no cap" if x.ceiling == 0 else f"{x.ceiling:g}×")
        fig, ax = plt.subplots(figsize=(10, 5.6))
        ax.imshow(mat, cmap="Greens", aspect="auto", origin="lower")
        ax.set_xticks(range(len(a.steps)), [f"{x:.0%}" for x in a.steps])
        ax.set_yticks(range(len(a.stocks)), [f"{y:.0%}" for y in a.stocks])
        ax.set_xlabel("Guardrail step (max real change / yr)", color=MUTED)
        ax.set_ylabel("Stocks (>100% = leveraged)", color=MUTED)
        vmin, vmax = np.nanmin(mat), np.nanmax(mat)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat[i, j]
                dark = not np.isnan(v) and (v - vmin) / max(vmax - vmin, 1e-9) > 0.6
                ax.text(j, i, esc(lab.get((i, j), "—")), ha="center", va="center", fontsize=7.5,
                        color="white" if dark else INK)
        for sp in ax.spines.values():
            sp.set_visible(False)
        what = "years 1–10" if a.rank == "early" else "all years"
        dtxt = "flat real spending" if d == 0 else f"real spending {d:+.1%}/yr"
        ftxt = f"floor ${a.target:g}" + ("" if a.flat_floor or d == 0 else f" declining {d:+.1%}/yr")
        ax.set_title(esc(f"Median spending, {what} ($ per $100) — {dtxt}, ≥{success:.1%} success, "
                         f"{ftxt}\ncell: spending / max safe start · best ceiling"),
                     loc="left", fontsize=10.5, color=INK, pad=8)
        fig.tight_layout(); fig.savefig(OUT / f"heatmap_drift{d:+.3f}.png", dpi=150); plt.close(fig)

    # ---- fan chart for the top pick
    rule = rule_for(top, a)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    paths = []
    for y in starts:
        p = st.simulate_path(df, y, top.max_rate, rule, top.stocks, a.horizon, a.timing)
        paths.append(p.real_spend.values * 100)
        fpath = a.target * (1 + (0 if a.flat_floor else top.drift)) ** np.arange(len(p))
        failed = p.shortfall.any() or (p.real_spend.values * 100 < fpath - 1e-9).any()
        ax.plot(range(1, len(p) + 1), p.real_spend * 100, lw=1.6 if failed else 0.8,
                color="#dc2626" if failed else "#2563eb", alpha=1 if failed else 0.3,
                label=f"{y} (failed)" if failed else None, zorder=3 if failed else 2)
    ax.plot(range(1, a.horizon + 1), np.median(np.array(paths), axis=0), color=INK, lw=2.2, label="Median retiree")
    ax.plot(range(1, a.horizon + 1), fpath, color=INK, lw=1, ls="--", label="Floor")
    style(ax, esc(f"Real spending, every retiree — {describe(top)}"), esc("Real $ per $100 start"))
    ax.set_xlabel("Year of retirement", color=MUTED)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "spending_fan_top_pick.png", dpi=150); plt.close(fig)

    # ---- spending shape: median and 5th-percentile path for a few reference strategies
    refs, seen = [], set()
    for label, cond in [("Top pick", ok.index == ok.index[0]),
                        ("Best flat-real plan", ok.drift == 0),
                        ("Constant spending, no guardrails", (ok.step == 0) & (ok.ceiling == 0) & (ok.drift == 0))]:
        c = ok[cond]
        if len(c) and c.index[0] not in seen:
            seen.add(c.index[0])
            refs.append((label, c.iloc[0]))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for (label, r), color in zip(refs, ["#2563eb", "#d97706", "#6b7280"]):
        P = np.array([st.simulate_path(df, y, r.max_rate, rule_for(r, a), r.stocks, a.horizon, a.timing)
                      .real_spend.values * 100 for y in starts])
        yrs = range(1, a.horizon + 1)
        ax.plot(yrs, np.median(P, axis=0), color=color, lw=2,
                label=esc(f"{label} ({r.max_rate:.1%} start): median"))
        ax.plot(yrs, np.percentile(P, 5, axis=0), color=color, lw=1.2, ls="--", label=esc(f"{label}: 5th pct"))
    ax.axhline(a.target, color=INK, lw=0.8, ls=":")
    style(ax, "Spending shape: typical vs. bad-luck retiree", esc("Real $ per $100 start"))
    ax.set_xlabel("Year of retirement", color=MUTED)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.14))
    fig.tight_layout(); fig.savefig(OUT / "spending_shape.png", dpi=150); plt.close(fig)

    # ---- report
    L = [f"# Best strategy search\n",
         f"{n} retirements ({starts[0]}–{starts[-1]}), {a.horizon} yrs. Success = real spending never below "
         f"${a.target:g} per $100 and never running out. Required success ≥ {success:.1%} "
         f"(≤ {allow} failed retirees). Stocks = {1 - a.intl:.0%} US / {a.intl:.0%} international"
         f"{' (stress series)' if a.intl_stress else ''}. "
         f"Band ±{a.band:.0%}; leverage at T-bills + {a.spread:.0%}. "
         + ("Floor stays flat.\n" if a.flat_floor else "With a negative drift the floor declines at the same rate.\n"),
         f"Ranked by median spending in **{'years 1–10' if a.rank == 'early' else 'all 30 years'}**. "
         "All values real $ per $100 of starting portfolio.\n",
         f"**Top pick:** {describe(top)}\n",
         "| Stocks | Step | Ceiling | Drift | Max start | Median yrs 1–10 | Median avg | Worst avg "
         "| Median final bal | Failed starts |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for _, x in ok.head(15).iterrows():
        L.append(f"| {x.stocks:.0%} | {x.step:.0%} | {'none' if x.ceiling == 0 else f'{x.ceiling:g}×'} "
                 f"| {x.drift:+.1%} | {x.max_rate:.1%} | ${x.median_early:.2f} | ${x.median_avg:.2f} "
                 f"| ${x.worst_avg:.2f} | ${x.median_final:.0f} | {x.failed_years or '—'} |")
    L.append("\n## Best per drift × ceiling\n")
    L.append("| Drift | Ceiling | Best mix | Max start | Median yrs 1–10 | Median avg | Failed starts |")
    L.append("|---|---|---|---|---|---|---|")
    for (d, c), g in ok.groupby(["drift", "ceiling"], sort=True):
        x = g.iloc[0]
        L.append(f"| {d:+.1%} | {'none' if c == 0 else f'{c:g}×'} | {x.stocks:.0%} / ±{x.step:.0%} "
                 f"| {x.max_rate:.1%} | ${x.median_early:.2f} | ${x.median_avg:.2f} | {x.failed_years or '—'} |")
    lev = res[res.stocks > 1]
    if len(lev):
        L.append(f"\nLeveraged mixes qualifying: {lev.max_rate.notna().sum()} of {len(lev)} combinations.")
    (OUT / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
