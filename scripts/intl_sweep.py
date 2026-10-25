"""How much does international diversification help a fixed spending strategy?

Sweeps the international share of the stock allocation and reports the highest
safe starting rate at 100% and 95% historical success, on both the base and the
stress international series.

    python scripts/intl_sweep.py
    python scripts/intl_sweep.py --stocks 0.9 --step 0.25 --ceiling 0 --drift 0
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
from optimize import evaluate, max_safe_rate, esc  # noqa: E402
from reproduce import style, MUTED  # noqa: E402

OUT = ROOT / "output" / "intl"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shares", default="0,0.1,0.2,0.25,0.3,0.4,0.5")
    ap.add_argument("--stocks", type=float, default=0.8)
    ap.add_argument("--step", type=float, default=0.30)
    ap.add_argument("--ceiling", type=float, default=2.0, help="0 = none")
    ap.add_argument("--drift", type=float, default=-0.005)
    ap.add_argument("--target", type=float, default=4.0)
    ap.add_argument("--band", type=float, default=0.20)
    a = ap.parse_args()
    shares = [float(x) for x in a.shares.split(",")]
    OUT.mkdir(parents=True, exist_ok=True)
    grid = np.round(np.arange(a.target / 100, 0.15001, 0.001), 4)
    ceiling = a.ceiling if a.ceiling > 0 else None

    rows = []
    for series in ("intl", "intl_stress"):
        base = data.load(intl_series=series)
        base = base.assign(bonds=0.5 * base.bills + 0.5 * base.bonds)
        starts = list(range(base.index.min(), base.index.max() - 28))
        for sh in shares:
            df = data.with_intl(base, sh)
            rets = st.portfolio_returns(df, a.stocks)
            W = [(list(rets.loc[y:y + 29]), list(df.inflation.loc[y:y + 29]), y) for y in starts]
            for success in (1.0, 0.95):
                allow = math.floor((1 - success) * len(starts) + 1e-9)
                b = max_safe_rate(W, a.step, a.band, a.target, ceiling, a.drift, "end", grid, allow, a.drift)
                r = b[0] + 0.001
                nxt = evaluate(W, r, a.step, a.band, min(1, a.target / 100 / r), ceiling, a.drift, "end",
                               a.target, a.drift)["failed_years"]
                rows.append({"series": series, "intl": sh, "success": success, "max_rate": b[0],
                             "median_early": b[1]["median_early"], "median_avg": b[1]["median_avg"],
                             "failed": b[1]["failed_years"], "breaks_next": nxt})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "intl_sweep.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for (series, success), g in res.groupby(["series", "success"]):
        ax.plot(g.intl * 100, g.max_rate * 100, marker="o",
                color="#2563eb" if success == 1 else "#d97706", ls="-" if series == "intl" else "--",
                label=f"{success:.0%} success · {'base' if series == 'intl' else 'stress'} series")
    c = "no cap" if not ceiling else f"cap {a.ceiling:g}×"
    style(ax, esc(f"Highest safe start vs. international share — {a.stocks:.0%} stocks, ±{a.step:.0%}, {c}, "
                  f"{a.drift:+.1%}/yr"), "Starting withdrawal rate (%)")
    ax.set_xlabel("International share of stocks (%)", color=MUTED)
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "intl_sweep.png", dpi=150); plt.close(fig)

    L = ["# International diversification sweep\n",
         f"Strategy: {a.stocks:.0%} stocks, ±{a.step:.0%} guardrails, {c}, {a.drift:+.1%}/yr real, "
         f"floor ${a.target:g} declining with drift. 69 retirements 1928–1996.\n",
         "| Series | Intl share | Success | Max safe start | Median yrs 1–10 | Median avg | Retirees that break next |",
         "|---|---|---|---|---|---|---|"]
    for _, x in res.iterrows():
        L.append(f"| {x.series} | {x.intl:.0%} | {x.success:.0%} | {x.max_rate:.1%} | ${x.median_early:.2f} "
                 f"| ${x.median_avg:.2f} | {x.breaks_next} |")
    (OUT / "results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
