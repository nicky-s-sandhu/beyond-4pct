"""Bengen-style historical withdrawal simulation.

Mechanics (Bengen, "Determining Withdrawal Rates Using Historical Data",
Journal of Financial Planning, Oct 1994):

* The retiree starts on Jan 1 of a given year with a portfolio of 1.0.
* First-year withdrawal = rate x initial portfolio. Each later withdrawal is
  the previous one raised by that year's CPI inflation (constant real spending).
* The portfolio is rebalanced every year to a fixed stock/bond mix.
* "Longevity" = number of years of withdrawals the portfolio can fund.

Bengen's data ended in 1992; for years after that he assumed long-run average
returns and inflation. `bengen1994_series()` recreates that setup, while the
`load()` data lets you run the same test on actual history through today.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Result:
    start_year: int
    years: float           # years of spending funded (fractional for the last partial year)
    depleted: bool         # False = still solvent when we hit max_years or the end of data
    final_balance: float   # nominal balance at the end (0 if depleted)


def portfolio_returns(df: pd.DataFrame, stock_share: float) -> pd.Series:
    return stock_share * df["stocks"] + (1 - stock_share) * df["bonds"]


def longevity(df: pd.DataFrame, start_year: int, rate: float, stock_share: float = 0.5,
              max_years: int = 50, timing: str = "start") -> Result:
    """How long does a `rate` withdrawal last for a retiree starting in `start_year`?

    timing="start": withdraw at the beginning of each year, then earn the return.
    timing="end":   earn the return, then withdraw at year end.
    """
    rets = portfolio_returns(df, stock_share)
    infl = df["inflation"]
    bal, wd, n = 1.0, rate, 0
    years = [y for y in df.index if y >= start_year][:max_years]
    for y in years:
        if timing == "start":
            if bal < wd:
                return Result(start_year, n + bal / wd, True, 0.0)
            bal = (bal - wd) * (1 + rets[y])
        else:
            bal *= 1 + rets[y]
            if bal < wd:
                return Result(start_year, n + bal / wd, True, 0.0)
            bal -= wd
        n += 1
        wd *= 1 + infl[y]
    return Result(start_year, float(n), False, bal)


def safemax(df: pd.DataFrame, start_year: int, horizon: int = 30, stock_share: float = 0.5,
            timing: str = "start", tol: float = 1e-5) -> float | None:
    """Highest initial rate that funds `horizon` full years for this start year.
    Returns None if the data doesn't cover the full horizon."""
    if len([y for y in df.index if y >= start_year]) < horizon:
        return None
    lo, hi = 0.0, 0.5
    while hi - lo > tol:
        mid = (lo + hi) / 2
        r = longevity(df, start_year, mid, stock_share, max_years=horizon, timing=timing)
        lo, hi = (mid, hi) if (not r.depleted and r.years >= horizon) else (lo, mid)
    return lo


def bengen1994_series(df: pd.DataFrame, last_actual: int = 1992, first_actual: int | None = None,
                      extend_to: int = 2030) -> pd.DataFrame:
    """Actual data through `last_actual`, then the historical average of each
    column (over the actual window) for every later year -- Bengen's approach."""
    first_actual = first_actual or df.index.min()
    hist = df.loc[first_actual:last_actual].copy()
    avg = hist.mean()  # arithmetic average, applied as a constant annual value
    future = pd.DataFrame([avg.values] * (extend_to - last_actual),
                          index=range(last_actual + 1, extend_to + 1), columns=df.columns)
    out = pd.concat([hist, future])
    out.index.name = "year"
    return out


def longevity_table(df: pd.DataFrame, start_years, rates, stock_share=0.5,
                    max_years=50, timing="start") -> pd.DataFrame:
    rows = []
    for y in start_years:
        for r in rates:
            res = longevity(df, y, r, stock_share, max_years, timing)
            rows.append({"start_year": y, "rate": r, "years": res.years,
                         "depleted": res.depleted})
    return pd.DataFrame(rows)
