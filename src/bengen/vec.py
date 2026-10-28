"""Vectorised engine: every retiree simulated at once (numpy arrays over start years).

Same mechanics as bucket.run (and so strategies.fast_guardrails), generalised:
  - separate cut and raise sizes (cut_step, raise_step) on a +/-band guardrail
  - floor and ceiling as multiples of the planned path (start x (1+drift)^t)
  - optional cash bucket (cash share taken from bonds, spent first in downturns)
All rates are decimals; returns arrays shaped (n_retirees, horizon).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class Params:
    rate: float = 0.04          # first-year withdrawal / starting portfolio
    stocks: float = 0.5         # stock share (US + intl), rest bonds + cash
    intl: float = 0.0           # international share of the stocks
    band: float = 0.20          # guardrails at rate x (1 +/- band)
    cut_step: float = 0.0       # real cut when above the upper guardrail (0 = no guardrails)
    raise_step: float = 0.0     # real raise when below the lower guardrail
    floor: float = 0.0          # spending floor as a multiple of the plan (0 = none)
    floor_flat: bool = False    # True: floor is a multiple of year-1 spending, fixed in real terms
    ceiling: float = 0.0        # spending cap as a multiple of the plan (0 = none)
    drift: float = 0.0          # planned real change in spending per year (years 1-10)
    drift2: float | None = None # years 11-20 (None = same as drift)
    drift3: float | None = None # years 21-30 (None = same as drift2)
    curve: str = ""             # "blanchett": planned change by age (Blanchett 2014), replaces drift/drift2/drift3
    start_age: int = 65
    expenditure: float = 75000.0  # household spending ($/yr) used in Blanchett's equation
    cash: float = 0.0           # cash share (taken from bonds)
    bucket: bool = False        # spend cash then bonds in downturns (else static cash)
    threshold: float = 0.10     # downturn = stocks this far below peak
    max_years: int = 5          # longest run of downturn years funded from cash/bonds
    refill_years: int = 5       # refill cash by target / refill_years in each up year

    def as_dict(self):
        return asdict(self)

    def drifts(self, T):
        """Per-year planned real change applied when moving from year t-1 to t (t = 0..T-1)."""
        if self.curve == "blanchett":
            return np.array([0.0] + [blanchett_change(self.start_age + t - 1, self.expenditure) for t in range(1, T)])
        d2 = self.drift if self.drift2 is None else self.drift2
        d3 = d2 if self.drift3 is None else self.drift3
        return np.array([0.0] + [self.drift if t < 10 else d2 if t < 20 else d3 for t in range(1, T)])

    def plan(self, T):
        """Planned real spending path per $1 start: rate x cumulative drift."""
        return self.rate * np.cumprod(1 + self.drifts(T))


def blanchett_change(age, expenditure=75000.0):
    """Real change in spending from `age` to age + 1: Blanchett (2014), 'Exploring the Retirement Consumption
    Puzzle', Journal of Financial Planning 27(5), equation 1. About -1%/yr on average from 65 to 95; gentlest
    early and late in retirement (the 'spending smile'), steepest around age 78."""
    return 0.00008 * age ** 2 - 0.0125 * age - 0.00661 * np.log(expenditure) + 0.546


def survival_weights(T=30, start_age=65, who="couple", path=None):
    """Probability of being alive (couple: at least one of a man and a woman) at the start of each year."""
    from pathlib import Path
    path = path or Path(__file__).resolve().parents[2] / "data" / "raw" / "ssa_period_life_2022.csv"
    lt = pd.read_csv(path).set_index("age")
    ages = range(start_age, start_age + T)
    sm = np.cumprod([1.0] + [1 - lt.q_male[a] for a in ages][:-1])
    sf = np.cumprod([1.0] + [1 - lt.q_female[a] for a in ages][:-1])
    return {"couple": 1 - (1 - sm) * (1 - sf), "male": sm, "female": sf, "single": (sm + sf) / 2,
            "none": np.ones(T)}[who]


def windows(df: pd.DataFrame, intl: float, horizon: int = 30):
    """Arrays (n, horizon) of stock, bond, bill returns and inflation for every full window."""
    stocks = (1 - intl) * df["stocks"] + intl * df["intl"] if intl > 0 else df["stocks"]
    starts = list(range(df.index.min(), df.index.max() - horizon + 2))
    take = lambda s: np.array([s.loc[y:y + horizon - 1].values for y in starts])
    return starts, take(stocks), take(df["bonds"]), take(df["bills"]), take(df["inflation"])


def simulate(p: Params, S_r, B_r, C_r, infl):
    """Returns dict of arrays: real spending (n, T), depleted (n,), final real balance (n,),
    real year-end balance (n, T)."""
    n, T = S_r.shape
    cash = p.cash if p.cash > 0 else 0.0
    bonds_w = max(1.0 - p.stocks - cash, 0.0)
    inv_s = p.stocks / (p.stocks + bonds_w) if p.stocks + bonds_w > 0 else 1.0
    S = np.full(n, p.stocks)
    B = np.full(n, bonds_w)
    C = np.full(n, cash)
    idx = np.ones(n)
    peak = np.ones(n)
    down_run = np.zeros(n, dtype=int)
    price = np.ones(n)
    spend = np.full(n, p.rate)
    reals = np.empty((n, T))
    balances = np.empty((n, T))
    depleted = np.zeros(n, dtype=bool)
    hi_g, lo_g = p.rate * (1 + p.band), p.rate * (1 - p.band)
    dr = p.drifts(T)
    plan_f = np.cumprod(1 + dr)
    for t in range(T):
        if t > 0:
            bal = S + B + C
            price = price * (1 + infl[:, t - 1])
            spend = spend * (1 + infl[:, t - 1]) * (1 + dr[t])
            if p.cut_step > 0 or p.raise_step > 0:
                with np.errstate(divide="ignore", invalid="ignore"):
                    wr = np.where(bal > 0, spend / np.where(bal > 0, bal, 1), np.inf)
                alive = bal > 0
                spend = np.where(alive & (wr > hi_g), spend * (1 - p.cut_step), spend)
                spend = np.where(alive & (wr < lo_g), spend * (1 + p.raise_step), spend)
            plan = p.rate * price * plan_f[t]
            if p.floor > 0:
                spend = np.maximum(spend, p.floor * (p.rate * price if p.floor_flat else plan))
            if p.ceiling > 0:
                spend = np.minimum(spend, p.ceiling * plan)
        S = S * (1 + S_r[:, t])
        B = B * (1 + B_r[:, t])
        C = C * (1 + C_r[:, t])
        idx = idx * (1 + S_r[:, t])
        peak = np.maximum(peak, idx)
        total = S + B + C
        take = np.minimum(spend, total)
        depleted |= take < spend - 1e-12
        if p.bucket and cash > 0:
            in_down = idx < peak * (1 - p.threshold)
            use_bucket = in_down & (down_run < p.max_years)
            down_run = np.where(use_bucket, down_run + 1, np.where(in_down, down_run, 0))
        else:
            use_bucket = np.zeros(n, dtype=bool)
        # bucket years: cash, then bonds, then stocks; no rebalancing
        x = take.copy()
        dC = np.minimum(x, C); xC = x - dC
        dB = np.minimum(xC, B); xB = xC - dB
        Sb, Bb, Cb = S - xB, B - dB, C - dC
        # normal years: withdraw, refill/hold cash, rebalance the rest
        tot_n = total - take
        tgt = cash * tot_n
        if p.bucket and cash > 0:
            Cn = np.where(C > tgt, tgt, np.where(S_r[:, t] > 0, np.minimum(tgt, C + tgt / p.refill_years), C))
            Cn = np.minimum(Cn, tot_n)
        else:
            Cn = tgt
        inv = tot_n - Cn
        Sn, Bn = inv * inv_s, inv * (1 - inv_s)
        S = np.where(use_bucket, Sb, Sn)
        B = np.where(use_bucket, Bb, Bn)
        C = np.where(use_bucket, Cb, Cn)
        reals[:, t] = take / price
        balances[:, t] = (S + B + C) / (price * (1 + infl[:, t]))
    final = (S + B + C) / (price * (1 + infl[:, T - 1]))
    return {"reals": reals, "depleted": depleted, "final": final, "balances": balances}


def metrics(p: Params, out, gamma: float = 3.0, subsistence: float = 0.01, weights=None):
    """Pain and score. Spending per $1 start (multiply by 100 for $ per $100).
    weights: per-year weights for the score (e.g. survival probabilities); None = equal."""
    reals = out["reals"]
    n, T = reals.shape
    plan = p.plan(T)
    w = np.ones(T) if weights is None else np.asarray(weights, dtype=float)
    w = w / w.sum()
    cut_plan = np.clip(1 - reals / plan, 0, None).max(axis=1)
    peak = np.maximum.accumulate(reals, axis=1)
    cut_peak = (1 - reals / peak).max(axis=1)
    ran_out = out["depleted"]
    c = np.maximum(reals, subsistence)
    if gamma == 1:
        ce = float(np.exp((np.log(c) * w).sum(axis=1).mean()))
    else:
        ce = float(((c ** (1 - gamma)) * w).sum(axis=1).mean() ** (1 / (1 - gamma)))
    lvl = np.select([ran_out, cut_plan >= 0.5 - 1e-9, cut_plan >= 0.3, cut_plan >= 0.15, cut_plan >= 0.05],
                    ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")
    return {
        "ce": ce * 100,
        "extreme_share": float(np.mean((cut_plan >= 0.5 - 1e-9) | ran_out)),
        "ran_out": int(ran_out.sum()),
        "severe_plus_share": float(np.mean((cut_plan >= 0.3) | ran_out)),
        "typical_1_10": float(np.median(reals[:, :10].mean(axis=1))) * 100,
        "typical_avg": float(np.median(reals.mean(axis=1))) * 100,
        "worst_year": float(reals.min()) * 100,
        "p10_year": float(np.percentile(reals, 10)) * 100,
        "median_final": float(np.median(out["final"])) * 100,
        "cut_peak_30_share": float(np.mean((cut_peak >= 0.3) | ran_out)),
        "years_15_below": float(np.median((1 - reals / plan >= 0.15).sum(axis=1))),
        "typical_11_20": float(np.median(reals[:, 10:20].mean(axis=1))) * 100,
        "typical_21_30": float(np.median(reals[:, 20:].mean(axis=1))) * 100,
        "planned_end": float(plan[-1] / plan[0]),
        "levels": lvl,
    }
