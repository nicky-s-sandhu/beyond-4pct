"""Valuation-aware asset allocation in retirement, as in Pfau and Kitces (2015), plus helpers for Kitces (2008)
and Pfau (2011).

Conventions follow those papers: fixed real withdrawals taken at the START of each year, then the portfolio is
rebalanced to that year's stock share and earns the year's real return (January to January). Allocation decisions
use the January PE10 (CAPE) and its median over all Januaries from 1881 up to and including that one (no hindsight).

With returns fixed by the allocation path (which does not depend on wealth), the highest sustainable fixed real
withdrawal over T years has a closed form:  w* = 1 / sum_{t=0}^{T-1} prod_{k<t} 1 / (1 + r_k).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load(path=None) -> pd.DataFrame:
    d = pd.read_csv(path or ROOT / "data" / "raw" / "shiller_annual.csv").set_index("year")
    # Optional international share of stocks (env BENGEN_INTL, e.g. 0.3): US real returns blended with developed
    # ex-US real returns, rebalanced yearly. The valuation signal stays the US CAPE.
    import os
    share = float(os.environ.get("BENGEN_INTL", "0") or 0)
    d["real_stocks_us"] = d["real_stocks"]
    if share > 0:
        d["real_stocks"] = (1 - share) * d["real_stocks"] + share * d["real_intl"]
    cape = d["cape_jan"]
    med = cape.expanding().median()               # inception-to-date median (NaNs before 1881 are skipped)
    d["cape_median"] = med
    d["cape_rel"] = cape / med
    # "normal" as the average of the last 10 Januaries' CAPE (this one included; nothing from the future)
    d["cape_avg10"] = cape.rolling(10).mean()
    d["cape_rel10"] = cape / d["cape_avg10"]
    return d


def ramp_shares(rel, s_min, s_max, s_mid, width):
    """Stock share that slides with valuation: s_mid when CAPE equals its 10-year average, falling linearly to s_min
    as CAPE rises `width` (e.g. 0.3 = 30%) above it, and rising linearly to s_max as it falls `width` below it."""
    dev = rel - 1.0
    up = s_mid - (s_mid - s_min) * np.clip(dev / width, 0, 1)
    down = s_mid + (s_max - s_mid) * np.clip(-dev / width, 0, 1)
    return np.where(dev >= 0, up, down)


@dataclass
class Strategy:
    """Stock share path: a glidepath start -> end over `years`, plus an optional valuation overlay.
    Valuation state: under if CAPE < lo x median, over if CAPE > hi x median (Graham and Dodd: 2/3 and 4/3).
    overlay: percentage points added when undervalued and subtracted when overvalued.
    bounds: clip the result to [floor, cap] (bounded variants) or None."""
    start: float = 0.6
    end: float | None = None      # None = static
    years: int = 30               # years to go from start to end (then hold)
    overlay: float = 0.0
    lo: float = 2 / 3
    hi: float = 4 / 3
    bounds: tuple | None = None
    under: float | None = None    # absolute stock share when undervalued (replaces start/overlay), as in the
    over: float | None = None     # standalone valuation rule (45% base, 60% under, 30% over)

    def shares(self, rel: np.ndarray) -> np.ndarray:
        """rel: (n, T) CAPE relative to its median at each January of each retirement."""
        n, T = rel.shape
        t = np.arange(T)
        if self.end is None:
            base = np.full(T, self.start)
        else:
            step = (self.end - self.start) / self.years
            base = np.where(t < self.years, self.start + step * t, self.end)
        s = np.tile(base, (n, 1))
        under, over = rel < self.lo, rel > self.hi
        if self.under is not None:
            s = np.where(under, self.under, s)
        if self.over is not None:
            s = np.where(over, self.over, s)
        if self.overlay:
            s = s + self.overlay * under - self.overlay * over
        if self.bounds is not None:
            s = np.clip(s, *self.bounds)
        return np.clip(s, 0.0, 1.0)


def windows(d: pd.DataFrame, starts, T=30, safe="bills", rel="cape_rel"):
    take = lambda col: np.array([d[col].loc[y:y + T - 1].values for y in starts])
    return take("real_stocks"), take(f"real_{safe}"), take(rel)


def path_returns(strategy: Strategy, S, B, rel):
    w = strategy.shares(rel)
    return w * S + (1 - w) * B, w


def safemax(R):
    """Highest fixed real withdrawal (share of the starting portfolio) lasting T years, start-of-year withdrawals."""
    disc = np.cumprod(np.concatenate([np.ones((len(R), 1)), 1 / (1 + R[:, :-1])], axis=1), axis=1)
    return 1 / disc.sum(axis=1)


def terminal_wealth(R, rate=0.04, start=100.0):
    W = np.full(len(R), start)
    for t in range(R.shape[1]):
        W = np.maximum(W - rate * start, 0) * (1 + R[:, t])
    return W


def state(rel, lo=2 / 3, hi=4 / 3):
    return np.where(rel < lo, "Undervalued", np.where(rel > hi, "Overvalued", "Fair"))


# Pfau and Kitces (2015) strategies
def kp_strategies():
    gp = {
        "Fixed 45%": Strategy(0.45),
        "Fixed 60%": Strategy(0.60),
        "Declining 60→30 (30 yrs)": Strategy(0.60, 0.30, 30),
        "Accel. declining 60→30 (15 yrs)": Strategy(0.60, 0.30, 15),
        "Rising 30→60 (30 yrs)": Strategy(0.30, 0.60, 30),
        "Accel. rising 30→60 (15 yrs)": Strategy(0.30, 0.60, 15),
    }
    out = dict(gp)
    out["Valuation 30/45/60"] = Strategy(0.45, under=0.60, over=0.30)
    for name in ["Declining 60→30 (30 yrs)", "Accel. declining 60→30 (15 yrs)", "Rising 30→60 (30 yrs)",
                 "Accel. rising 30→60 (15 yrs)"]:
        g = gp[name]
        out[f"{name} + valuation, bounded"] = Strategy(g.start, g.end, g.years, overlay=0.15, bounds=(0.30, 0.60))
        out[f"{name} + valuation, unbounded"] = Strategy(g.start, g.end, g.years, overlay=0.15)
    return out


def elevated_run(rel: pd.Series, hi: float, decay: str = "reset") -> pd.Series:
    """Years CAPE has been elevated (rel > hi) as of each January, the current one included.
    decay = "reset": back to 0 the first January CAPE is not elevated; "gradual": falls by 1 a year instead."""
    run, out = 0.0, {}
    for y, r in rel.items():
        if np.isnan(r):
            out[y] = np.nan
            continue
        if r > hi:
            run += 1
        else:
            run = 0.0 if decay == "reset" else max(run - 1, 0.0)
        out[y] = run
    return pd.Series(out)


def duration_shares(run, rel, s_min, s_normal, s_max, ramp_years, lo=2 / 3, cheap_years=0, cheap_run=None):
    """Stock share that bends slowly towards s_min the longer CAPE stays elevated: s_normal after 0 elevated years,
    s_min after `ramp_years`. When CAPE is cheap (rel < lo) the share moves to s_max: at once (cheap_years = 0) or
    over `cheap_years` consecutive cheap years (cheap_run counts them)."""
    frac = np.clip(run / ramp_years, 0, 1)
    s = s_normal - (s_normal - s_min) * frac
    if cheap_years == 0:
        s = np.where(rel < lo, s_max, s)
    else:
        s = np.where(rel < lo, s_normal + (s_max - s_normal) * np.clip(cheap_run / cheap_years, 0, 1), s)
    return s
