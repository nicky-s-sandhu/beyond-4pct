"""Stock share that moves with valuation, tested inside the recommended withdrawal plan.

A stock rule sets each January's stock share from that January's valuation signal (no hindsight):

    target_t = clip(c + k_cheap * max(x_t, 0) + k_dear * min(x_t, 0), lo, hi)
    share_t  = share_{t-1} + speed * (target_t - share_{t-1})       (share_0 = target_0)

x_t > 0 means stocks are cheap. Signals (all known in January of year t):
  "cape":  x = -ln(CAPE / median CAPE to date)                    (Pfau-Kitces style, continuous)
  "ecy":   x = (ECY - median ECY to date) / 8%, ECY = 1/CAPE - (10-yr Treasury yield - inflation over the past
           10 years), Shiller's excess CAPE yield (an equity risk premium measure)
  "none":  x = 0 (a fixed mix, the baseline)

The withdrawal engine is vec.simulate without the cash bucket, generalised to a stock share that varies by
retiree and year; with a constant share it reproduces vec.simulate exactly (tests/test_stockrule.py).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import vec

ROOT = Path(__file__).resolve().parents[2]
# January 10-year Treasury yields after Shiller's file ends (FRED GS10 January averages, via multpl.com)
GS10_JAN_EXTRA = {2023: 0.0353, 2024: 0.0406, 2025: 0.0463, 2026: 0.0421}


@dataclass(frozen=True)
class Rule:
    signal: str = "none"
    c: float = 0.8          # share when valuation is normal (x = 0)
    k_cheap: float = 0.0    # extra stocks per unit of cheapness
    k_dear: float = 0.0     # fewer stocks per unit of dearness
    lo: float = 0.0
    hi: float = 1.0
    speed: float = 1.0      # 1 = move to the target at once; 0.25 = close a quarter of the gap each year

    def as_dict(self):
        return asdict(self)

    def label(self):
        if self.signal == "none":
            return f"Fixed {self.c:.0%}"
        sp = "" if self.speed == 1 else f", speed {self.speed:g}"
        return (f"{self.signal.upper()}: {self.c:.0%} normal, +{self.k_cheap:g}/-{self.k_dear:g}, "
                f"{self.lo:.0%}-{self.hi:.0%}{sp}")


def signals(extra_inflation: pd.Series | None = None) -> pd.DataFrame:
    """January valuation signals by year, 1881 onward."""
    cape = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
    sh = pd.read_csv(ROOT / "data" / "raw" / "shiller_annual.csv").set_index("year")
    cape = cape.loc[1881:]
    rel = cape / cape.expanding().median()
    gs10 = sh["gs10_jan"].reindex(cape.index)
    for y, v in GS10_JAN_EXTRA.items():
        if y in gs10.index:
            gs10.loc[y] = v
    infl = sh["inflation"].copy()
    if extra_inflation is not None:
        infl = infl.combine_first(extra_inflation)
    infl = infl.reindex(infl.index.union(cape.index))
    trail = infl.rolling(10).mean().shift(1).reindex(cape.index)      # inflation over the 10 years before Jan y
    ecy = 1 / cape - (gs10 - trail)
    out = pd.DataFrame({"cape": cape, "rel": rel, "x_cape": -np.log(rel), "ecy": ecy})
    out["x_ecy"] = (ecy - ecy.expanding(min_periods=10).median()) / 0.08
    out["x_none"] = 0.0
    return out


def shares(rule: Rule, X: np.ndarray) -> np.ndarray:
    """X: (n, T) signal (positive = cheap). Returns the stock share (n, T)."""
    if rule.signal == "none":
        return np.full(X.shape, rule.c)
    tgt = np.clip(rule.c + rule.k_cheap * np.maximum(X, 0) + rule.k_dear * np.minimum(X, 0), rule.lo, rule.hi)
    if rule.speed >= 1:
        return tgt
    W = np.empty_like(tgt)
    W[:, 0] = tgt[:, 0]
    for t in range(1, tgt.shape[1]):
        W[:, t] = W[:, t - 1] + rule.speed * (tgt[:, t] - W[:, t - 1])
    return W


def simulate(p: vec.Params, W, S_r, B_r, infl):
    """vec.simulate (no cash bucket) with stock share W (n, T) chosen each January."""
    n, T = S_r.shape
    R = W * S_r + (1 - W) * B_r
    total = np.ones(n)
    price = np.ones(n)
    spend = np.full(n, p.rate)
    reals = np.empty((n, T))
    depleted = np.zeros(n, dtype=bool)
    hi_g, lo_g = p.rate * (1 + p.band), p.rate * (1 - p.band)
    plan_f = np.cumprod(1 + p.drifts(T))
    dr = p.drifts(T)
    for t in range(T):
        if t > 0:
            price = price * (1 + infl[:, t - 1])
            spend = spend * (1 + infl[:, t - 1]) * (1 + dr[t])
            if p.cut_step > 0 or p.raise_step > 0:
                alive = total > 0
                wr = np.where(alive, spend / np.where(alive, total, 1), np.inf)
                spend = np.where(alive & (wr > hi_g), spend * (1 - p.cut_step), spend)
                spend = np.where(alive & (wr < lo_g), spend * (1 + p.raise_step), spend)
            plan = p.rate * price * plan_f[t]
            if p.floor > 0:
                spend = np.maximum(spend, p.floor * (p.rate * price if p.floor_flat else plan))
            if p.ceiling > 0:
                spend = np.minimum(spend, p.ceiling * plan)
        total = total * (1 + R[:, t])
        take = np.minimum(spend, total)
        depleted |= take < spend - 1e-12
        total = total - take
        reals[:, t] = take / price
    final = total / (price * (1 + infl[:, T - 1]))
    return {"reals": reals, "depleted": depleted, "final": final}


def rate_at(p: vec.Params, W, S_r, B_r, infl, target=0.02, lo=0.03, hi=0.10, iters=10):
    """Highest starting rate (to ~0.01 point) with at most `target` of retirements running out."""
    from dataclasses import replace
    ok = lo
    for _ in range(iters):
        mid = (lo + hi) / 2
        if simulate(replace(p, rate=mid), W, S_r, B_r, infl)["depleted"].mean() <= target:
            ok, lo = mid, mid
        else:
            hi = mid
    return ok
