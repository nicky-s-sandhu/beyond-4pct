"""Numbers for docs/following-the-plan.md: Blanchett yearly changes by age and a worked example
(a $1 million retirement starting January 2000, actual returns), following the recommended plan exactly.

    python scripts/plan_guide_numbers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from bengen import vec  # noqa: E402
import model  # noqa: E402


def table():
    print("| Age | Planned change | Age | Planned change | Age | Planned change |")
    print("|---|---|---|---|---|---|")
    ages = list(range(65, 95))
    for i in range(10):
        cells = []
        for a in (ages[i], ages[i + 10], ages[i + 20]):
            cells += [f"{a} → {a + 1}", f"{vec.blanchett_change(a) * 100:+.1f}%"]
        print("| " + " | ".join(cells) + " |")
    for E in (50000, 75000, 100000):
        d = [vec.blanchett_change(a, E) for a in ages[:-1]]
        print(E, f"avg {np.mean(d) * 100:.2f}%  cum {(np.prod(1 + np.array(d)) - 1) * 100:.0f}%")


def example(start=2000, years=26, W0=1_000_000):
    s = model.RECOMMENDED
    p = model.to_params(s)
    df = model._frame(s["bonds"], s["intl_series"])
    yrs = list(range(start, start + years))
    S = ((1 - p.intl) * df["stocks"] + p.intl * df["intl"]).loc[yrs].values
    B = df["bonds"].loc[yrs].values
    I = df["inflation"].loc[yrs].values
    dr = p.drifts(years)
    rate, hi, lo = p.rate, p.rate * (1 + p.band), p.rate * (1 - p.band)
    W = W0
    first = rate * W0
    price, plan_f = 1.0, 1.0
    spend = first
    rows = []
    for t in range(years):
        action = "first year"
        jan = W
        if t > 0:
            price *= 1 + I[t - 1]
            plan_f *= 1 + dr[t]
            base = spend * (1 + I[t - 1]) * (1 + dr[t])
            wr = base / jan
            new = base
            action = "no change"
            if wr > hi:
                new, action = base * (1 - p.cut_step), "cut 8.5%"
            elif wr < lo:
                new, action = base * (1 + p.raise_step), "raise 15%"
            cap = p.ceiling * first * price * plan_f
            floor = p.floor * first * price
            if new > cap:
                new, action = cap, action + ", held to cap"
            if new < floor:
                new, action = floor, action + ", held to floor"
            spend = new
        else:
            wr = rate
        W = W * (1 + p.stocks * S[t] + (1 - p.stocks) * B[t]) - spend
        rows.append((yrs[t], 65 + t, I[t - 1] if t else float("nan"), dr[t] if t else float("nan"), jan, wr, action, spend,
                     spend / price, W))
    # cross-check with the engine on the same window
    out = vec.simulate(p, S[None, :], B[None, :], np.zeros((1, years)), I[None, :])
    assert np.allclose(out["reals"][0] * W0, [r[8] for r in rows]), "worksheet differs from engine"
    print(f"| Year | Age | Last year's inflation | Planned change | Portfolio, Jan 1 | Withdrawal rate | Action | Spending | Spending in {start} dollars |")
    print("|---|---|---|---|---|---|---|---|---|")
    for y, a, inf, d, jan, wr, act, sp, real, _ in rows:
        print(f"| {y} | {a} | {'' if np.isnan(inf) else f'{inf*100:.1f}%'} | {'' if np.isnan(d) else f'{d*100:+.1f}%'} | "
              f"${jan:,.0f} | {wr*100:.1f}% | {act} | ${sp:,.0f} | ${real:,.0f} |")
    print("end balance", f"${rows[-1][9]:,.0f}", "real", f"${rows[-1][9] / (price * (1 + I[-1])):,.0f}")


if __name__ == "__main__":
    table()
    example()
