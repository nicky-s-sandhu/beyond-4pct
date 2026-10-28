"""Numbers for the write-up: the recommended plan vs the earlier plan and Bengen's 4% rule, in real history,
with fees, and across 5,000 reshuffled-history retirements. Prints a markdown table (per $1M saved).

    python scripts/plan_summary.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import model  # noqa: E402
from bengen import vec  # noqa: E402

PLANS = ["Recommended plan", "Earlier plan (6.1% start, 75% floor)", "Bengen 4% (50/50 US)"]


def boot(settings, fee=0.0):
    p = model.to_params(settings)
    US, INTL, B, C, I = model._boot(settings["bonds"], settings["intl_series"])
    S = (1 - p.intl) * US + p.intl * INTL if p.intl > 0 else US
    out = vec.simulate(p, S - fee, B - fee, C - fee, I)
    w = vec.survival_weights(30, who=settings["who"])
    return out, vec.metrics(p, out, gamma=settings["gamma"], weights=w)


def hist_fee(settings, fee):
    p = model.to_params(settings)
    starts, S, B, C, I = model._windows(settings["bonds"], settings["intl_series"], round(p.intl, 4))
    return int(vec.simulate(p, S - fee, B - fee, C - fee, I)["depleted"].sum())


def main():
    k = lambda v: f"${v * 1e4:,.0f}"
    rows = {}
    for name in PLANS:
        s = model.PRESETS[name]
        r = model.run(s)
        ob, mb = boot(s)
        R = ob["reals"] * 100
        low = np.where(ob["depleted"], 0, R.min(axis=1))
        rows[name] = {
            "First-year spending": k(s["rate"]),
            "Floor (never below)": k(r.floor[0]) if r.floor.any() else "none",
            "Score, real history": f"${r.m['ce']:.2f}",
            "Score, reshuffled history": f"${mb['ce']:.2f}",
            "Ran out, real history (of 69)": str(r.m["ran_out"]),
            "Ran out, real history, 0.25% / 0.5% fee": f"{hist_fee(s, .0025)} / {hist_fee(s, .005)}",
            "Ran out, reshuffled history": f"{ob['depleted'].mean():.1%}",
            "Ran out, reshuffled, 0.25% fee": f"{boot(s, .0025)[0]['depleted'].mean():.1%}",
            "Typical spending yr 1 / 10 / 20 / 30 (reshuffled)": " / ".join(k(np.median(R[:, t]))
                                                                       for t in (0, 9, 19, 29)),
            "Ever below $30,000 (reshuffled)": f"{np.mean(low < 3):.0%}",
            "Typical balance at year 30 (reshuffled), per $1M": k(mb["median_final"]),
        }
    keys = list(next(iter(rows.values())))
    print("| | " + " | ".join(PLANS) + " |")
    print("|---|" + "---|" * len(PLANS))
    for key in keys:
        print(f"| {key} | " + " | ".join(rows[n][key] for n in PLANS) + " |")


if __name__ == "__main__":
    main()
