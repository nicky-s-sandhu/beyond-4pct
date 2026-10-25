"""Show how the ±30% guardrails act, year by year, for a bad and a good retiree.

Plan: 8.0% start, 80% stocks (25% of them international), ±30% guardrails on a
±20% band, real spending -0.5%/yr, $4 floor declining with it, 2x cap.

Each year:
  1. planned spending = last year's x (1 + inflation) x (1 - 0.5%)
  2. trigger = planned spending / current portfolio
  3. trigger > 8.0% x 1.2 = 9.6%  -> cut spending 30%
     trigger < 8.0% x 0.8 = 6.4%  -> raise spending 30%
  4. clamp to the floor ($4 real, -0.5%/yr) and the cap (2x the planned path)

    python scripts/explain_guardrails.py [--years 1966,1982]
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
from bengen import data, strategies as st  # noqa: E402

OUT = ROOT / "output" / "variants"
RATE, STOCKS, INTL, STEP, BAND, CAP, DRIFT, FLOOR = 0.08, 0.8, 0.25, 0.30, 0.20, 2.0, -0.005, 4.0
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
LINE, BAND_C, CUT, RAISE = "#2a78d6", "#f0efec", "#d03b3b", "#0ca30c"


def trace(df, start, horizon=30):
    """Year-by-year decisions; real figures per $100 start, in start-year dollars."""
    rets = st.portfolio_returns(df, STOCKS)
    bal, price, spend, rows = 1.0, 1.0, RATE, []
    for i, y in enumerate(range(start, start + horizon)):
        trig, action, planned = RATE, "start", spend
        if i > 0:
            price *= 1 + df.inflation[y - 1]
            spend *= (1 + df.inflation[y - 1]) * (1 + DRIFT)
            planned = spend
            trig, action = spend / bal, "hold"
            if trig > RATE * (1 + BAND):
                spend *= 1 - STEP
                action = "cut"
            elif trig < RATE * (1 - BAND):
                spend *= 1 + STEP
                action = "raise"
            floor = (FLOOR / 100) * price * (1 + DRIFT) ** i
            cap = CAP * RATE * price * (1 + DRIFT) ** i
            if spend < floor:
                spend, action = floor, action + ", floor"
            if spend > cap:
                spend, action = cap, action + ", cap"
        bal *= 1 + rets[y]
        take = min(spend, bal)
        bal -= take
        moved = "down" if take < planned * (1 - 1e-9) else ("up" if take > planned * (1 + 1e-9) else "none")
        rows.append({"year": y, "n": i + 1, "trigger_pct": trig * 100, "action": action, "moved": moved,
                     "real_spend": take / price * 100, "floor": FLOOR * (1 + DRIFT) ** i,
                     "real_balance": bal / (price * (1 + df.inflation[y])) * 100})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1966,1982")
    a = ap.parse_args()
    years = [int(x) for x in a.years.split(",")]
    OUT.mkdir(parents=True, exist_ok=True)
    df = data.load()
    df = data.with_intl(df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds), INTL)

    # cross-check against the library engine
    rule = st.Guardrails(step=STEP, band=BAND, floor=FLOOR / 100 / RATE, ceiling=CAP, drift=DRIFT,
                         floor_follows_drift=True)
    traces = {}
    for y in years:
        t = trace(df, y)
        ref = st.simulate_path(df, y, RATE, rule, STOCKS, 30, "end")
        assert np.allclose(t.real_spend.values, ref.real_spend.values * 100), y
        traces[y] = t
        t.to_csv(OUT / f"guardrail_trace_{y}.csv", index=False)

    fig, axes = plt.subplots(2, len(years), figsize=(6 * len(years), 7.2), sharex="col",
                             gridspec_kw={"height_ratios": [1, 1]})
    axes = np.atleast_2d(axes).reshape(2, len(years))
    hi, lo = RATE * (1 + BAND) * 100, RATE * (1 - BAND) * 100
    ymax_t = 20  # higher triggers are clipped and noted
    ymax_s = max(t.real_spend.max() for t in traces.values()) * 1.15
    for j, y in enumerate(years):
        t = traces[y]
        cut = t[t.action.str.startswith("cut") & (t.moved == "down")]
        rise = t[t.action.str.startswith("raise") & (t.moved == "up")]
        held = t[(t.action.str.startswith("cut") | t.action.str.startswith("raise")) & (t.moved == "none")]
        ax = axes[0, j]
        ax.axhspan(lo, hi, color=BAND_C, zorder=0)
        for v, lab, dy in ((hi, f"cut above {hi:.1f}%", 7), (lo, f"raise below {lo:.1f}%", -7)):
            ax.axhline(v, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=1)
            ax.annotate(lab, (t.n.iloc[-1] + 0.6, v), xytext=(0, dy), textcoords="offset points",
                        va="center", fontsize=8, color=MUTED)
        tp = t.trigger_pct.clip(upper=ymax_t)
        ax.plot(t.n, tp, color=LINE, lw=2, zorder=3)
        ax.scatter(cut.n, cut.trigger_pct.clip(upper=ymax_t), marker="v", s=60, color=CUT, zorder=4,
                   label="Cut 30%")
        ax.scatter(rise.n, rise.trigger_pct.clip(upper=ymax_t), marker="^", s=60, color=RAISE, zorder=4,
                   label="Raise 30%")
        ax.scatter(held.n, held.trigger_pct.clip(upper=ymax_t), marker="o", s=34, facecolor="white",
                   edgecolor=MUTED, lw=1.3, zorder=4, label="Blocked by floor or cap")
        over = t[t.trigger_pct > ymax_t]
        if len(over):
            ax.text(t.n.iloc[-1], 2.0, f"clipped: off scale from year {over.n.iloc[0]}, "
                    f"peak {t.trigger_pct.max():.0f}%", ha="right", va="center", fontsize=8, color=MUTED)
        ax.set_ylim(0, ymax_t)
        on_floor = t.action.str.contains("floor").sum()
        plural = lambda k, w: f"{k} {w}{'' if k == 1 else 's'}"
        sub = f"; at the floor {on_floor} of 30 years" if on_floor else ""
        ax.set_title(f"Retired {y}: {plural(len(cut), 'cut')}, {plural(len(rise), 'raise')}{sub}", loc="left",
                     fontsize=11, color=INK)
        if j == 0:
            ax.set_ylabel("Withdrawal rate before adjusting (%)", color=MUTED, fontsize=9)
            ax.legend(frameon=False, fontsize=8, loc="upper left")

        ax = axes[1, j]
        ax.plot(t.n, t.floor, color=MUTED, lw=1, ls=(0, (4, 3)))
        ax.text(t.n.iloc[-1] + 0.6, t.floor.iloc[-1], "\\$4 floor\n(−0.5%/yr)", va="center", fontsize=8,
                color=MUTED)
        ax.step(t.n, t.real_spend, where="mid", color=LINE, lw=2, zorder=3)
        ax.scatter(cut.n, cut.real_spend, marker="v", s=60, color=CUT, zorder=4)
        ax.scatter(rise.n, rise.real_spend, marker="^", s=60, color=RAISE, zorder=4)
        ax.scatter(held.n, held.real_spend, marker="o", s=34, facecolor="white", edgecolor=MUTED, lw=1.3,
                   zorder=4)
        ax.set_ylim(0, ymax_s)
        ax.set_xlabel("Year of retirement", color=MUTED, fontsize=9)
        if j == 0:
            ax.set_ylabel("Real spending per \\$100 start (\\$)", color=MUTED, fontsize=9)
        last = t.iloc[-1]
        ax.annotate(f"ends with \\${last.real_balance:.0f} left", (last.n, last.real_spend), xytext=(0, -14),
                    textcoords="offset points", ha="right", va="top", fontsize=8, color=MUTED)
    for ax in axes.flat:
        ax.grid(axis="y", color=GRID_C, lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GRID_C)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.set_xlim(0.5, 34)
    fig.suptitle("How ±30% guardrails act: a cut or raise only when the withdrawal rate leaves the 6.4–9.6% band",
                 x=0.04, ha="left", fontsize=12.5, color=INK, y=0.985)
    fig.text(0.04, 0.935, "8.0% start, 80% stocks (25% international), real spending −0.5%/yr, "
             "\\$4 floor and 2× cap. Real dollars per \\$100 of starting portfolio.", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "guardrails_explained.png", dpi=150)
    plt.close(fig)

    # statistics across all retirees
    allt = [trace(df, y) for y in range(df.index.min(), df.index.max() - 28)]
    eff = lambda t, k: (t.action.str.startswith(k) & (t.moved == ("down" if k == "cut" else "up"))).sum()
    cuts = np.array([eff(t, "cut") for t in allt])
    raises = np.array([eff(t, "raise") for t in allt])
    floor_yrs = np.array([t.action.str.contains("floor").sum() for t in allt])
    first_cut = [t.loc[t.action.str.startswith("cut") & (t.moved == "down"), "n"].min() for t in allt]
    print(f"retirees: {len(allt)}")
    print(f"cuts per retiree: median {np.median(cuts):.0f}, max {cuts.max()}; retirees with no cut: {(cuts == 0).sum()}")
    print(f"raises per retiree: median {np.median(raises):.0f}, max {raises.max()}")
    print(f"first cut: median year {np.nanmedian(first_cut):.0f}")
    print(f"years where the floor overrode the rule: median {np.median(floor_yrs):.0f} per retiree")
    yrs = sum(len(t) - 1 for t in allt)
    print(f"share of years with an effective cut: {cuts.sum() / yrs:.0%}; raise: {raises.sum() / yrs:.0%}; "
          f"no change beyond inflation and drift: {1 - (cuts.sum() + raises.sum() + floor_yrs.sum()) / yrs:.0%}")
    print(f"retirees ever held at the floor: {(floor_yrs > 0).sum()}")


if __name__ == "__main__":
    main()
