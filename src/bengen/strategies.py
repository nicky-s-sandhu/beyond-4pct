"""Spending rules beyond Bengen's constant-real withdrawal.

Every rule answers one question each year: given last year's spending, this
year's inflation and the current balance, how much do we spend this year?

`simulate_path()` runs a rule for one retiree and returns the full year-by-year
path (balance, nominal and real spending), so any metric can be computed.

Rules
-----
ConstantReal   Bengen (1994): last year's spending raised by inflation, always.
Guardrails     Guyton-Klinger style: start from the inflation-adjusted amount,
               then cut or raise spending by `step` whenever the current
               withdrawal rate drifts outside a band around the initial rate.

`step` is the variance knob: it is the largest real change in spending the
rule will make in a single year. step=0 reproduces Bengen exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ConstantReal:
    name: str = "Constant real (Bengen)"

    def spend(self, prev: float, infl: float, bal: float, ctx: dict) -> float:
        return prev * (1 + infl)


@dataclass
class Guardrails:
    """Guyton-Klinger guardrails.

    step   real % change applied when a guardrail is hit (the variance knob)
    band   guardrails sit at initial_rate*(1-band) and initial_rate*(1+band)
    floor / ceiling
           optional limits on real spending as a multiple of year-1 spending
           (e.g. floor=0.8 never lets real spending fall below 80% of the start)
    skip_inflation_after_loss
           GK "portfolio management rule": no inflation raise after a year in
           which the portfolio lost money and the withdrawal rate is above initial
    no_cuts_last
           GK turn off the cut rule in the final N years of the horizon
    drift  planned real change in spending per year, e.g. -0.005 = spending
           rises 0.5% less than inflation each year (front-loaded retirement).
           The ceiling follows this declining path; the floor does too if
           floor_follows_drift=True (otherwise it stays flat in real terms).
    """
    step: float = 0.10
    band: float = 0.20
    floor: float | None = None
    ceiling: float | None = None
    skip_inflation_after_loss: bool = False
    no_cuts_last: int = 0
    drift: float = 0.0
    floor_follows_drift: bool = False
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = f"Guardrails ±{self.step:.0%}"

    def spend(self, prev: float, infl: float, bal: float, ctx: dict) -> float:
        init_rate = ctx["initial_rate"]
        wr_prev = prev / bal if bal > 0 else np.inf
        raise_infl = not (self.skip_inflation_after_loss and ctx["last_return"] < 0 and wr_prev > init_rate)
        s = prev * (1 + infl) if raise_infl else prev
        s *= 1 + self.drift
        if self.step > 0 and bal > 0:
            wr = s / bal
            cuts_allowed = ctx["years_left"] > self.no_cuts_last
            if wr > init_rate * (1 + self.band) and cuts_allowed:
                s *= 1 - self.step
            elif wr < init_rate * (1 - self.band):
                s *= 1 + self.step
        real0 = ctx["initial_spend"] * ctx["price_level"]  # year-1 spending in today's dollars
        if self.floor is not None:
            fd = (1 + self.drift) ** ctx["year_index"] if self.floor_follows_drift else 1.0
            s = max(s, self.floor * real0 * fd)
        if self.ceiling is not None:
            s = min(s, self.ceiling * real0 * (1 + self.drift) ** ctx["year_index"])
        return s


def simulate_path(df: pd.DataFrame, start_year: int, rate: float, rule, stock_share: float = 0.5,
                  horizon: int = 30, timing: str = "end") -> pd.DataFrame:
    """Year-by-year path for one retiree. Starting balance 1.0.

    Columns: year, balance_start, spend (nominal), real_spend (in start-year
    dollars), shortfall (True when the balance couldn't cover planned spending),
    balance_end, real_balance_end.
    """
    years = [y for y in df.index if y >= start_year][:horizon]
    rets = portfolio_returns(df, stock_share)  # supports leverage (stock_share > 1)
    infl = df["inflation"]
    bal, price, spend, last_ret = 1.0, 1.0, rate, 0.0
    rows = []
    for i, y in enumerate(years):
        if i > 0:
            prev_y = years[i - 1]
            price *= 1 + infl[prev_y]
            ctx = {"initial_rate": rate, "initial_spend": rate, "price_level": price,
                   "last_return": last_ret, "years_left": horizon - i, "year_index": i}
            spend = rule.spend(spend, infl[prev_y], bal, ctx)
        b0 = bal
        if timing == "start":
            take = min(spend, bal)
            bal = (bal - take) * (1 + rets[y])
        else:
            bal *= 1 + rets[y]
            take = min(spend, bal)
            bal -= take
        last_ret = rets[y]
        rows.append({"year": y, "balance_start": b0, "spend": take, "planned": spend,
                     "real_spend": take / price, "shortfall": take < spend - 1e-12,
                     "balance_end": bal, "real_balance_end": bal / (price * (1 + infl[y]))})
    return pd.DataFrame(rows)


def path_metrics(p: pd.DataFrame, rate: float) -> dict:
    """Summary numbers for one path. Real spending is in $ per $100 of starting portfolio."""
    rs = p["real_spend"] * 100
    chg = rs.pct_change().dropna()
    return {
        "depleted": bool(p["shortfall"].any()),
        "years_funded": int((~p["shortfall"]).sum()),
        "min_real_spend": rs.min(),
        "avg_real_spend": rs.mean(),
        "total_real_spend": rs.sum(),
        "min_vs_initial": rs.min() / (rate * 100),
        "max_yearly_cut": -chg.min() if len(chg) else 0.0,
        "yearly_vol": chg.std() if len(chg) > 1 else 0.0,
        "years_below_90pct": int((rs < 0.9 * rate * 100).sum()),
        "final_real_balance": p["real_balance_end"].iloc[-1] * 100,
    }


def run_all(df: pd.DataFrame, start_years, rate: float, rule, stock_share=0.5,
            horizon=30, timing="end") -> pd.DataFrame:
    out = []
    for y in start_years:
        m = path_metrics(simulate_path(df, y, rate, rule, stock_share, horizon, timing), rate)
        m["start_year"] = y
        out.append(m)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- fast kernel
def portfolio_returns(df: pd.DataFrame, stock_share: float, borrow_spread: float = 0.01) -> pd.Series:
    """Annually rebalanced stock/bond mix. stock_share > 1 means leverage:
    the extra stock exposure is financed at the T-bill rate + `borrow_spread`."""
    if stock_share <= 1:
        return stock_share * df["stocks"] + (1 - stock_share) * df["bonds"]
    return stock_share * df["stocks"] - (stock_share - 1) * (df["bills"] + borrow_spread)


def fast_guardrails(rets, infl, rate, step, band=0.2, floor=None, ceiling=None, timing="end",
                    drift=0.0, early_years=10, floor_drift=0.0):
    """Plain-float version of simulate_path(... Guardrails ...) for searches.
    rets/infl: lists for the retiree's years.
    floor_drift: the floor declines (or rises) by this real % per year; min_real is
    then measured against that declining floor path (real_i / (1+floor_drift)^i).
    Returns (depleted, min_real, avg_real, final_real_bal, avg_real_first_`early_years`)."""
    bal, price, spend = 1.0, 1.0, rate
    lo_g, hi_g = rate * (1 + band), rate * (1 - band)
    reals, depleted = [], False
    for i in range(len(rets)):
        if i > 0:
            price *= 1 + infl[i - 1]
            spend *= (1 + infl[i - 1]) * (1 + drift)
            if step > 0 and bal > 0:
                wr = spend / bal
                if wr > lo_g:
                    spend *= 1 - step
                elif wr < hi_g:
                    spend *= 1 + step
            if floor is not None:
                spend = max(spend, floor * rate * price * (1 + floor_drift) ** i)
            if ceiling is not None:
                spend = min(spend, ceiling * rate * price * (1 + drift) ** i)
        if timing == "start":
            take = min(spend, bal); bal = (bal - take) * (1 + rets[i])
        else:
            bal *= 1 + rets[i]; take = min(spend, bal); bal -= take
        if take < spend - 1e-12:
            depleted = True
        reals.append(take / price)
    final = bal / (price * (1 + infl[len(rets) - 1]))
    early = reals[:early_years]
    min_adj = min(x / (1 + floor_drift) ** k for k, x in enumerate(reals))
    return depleted, min_adj, sum(reals) / len(reals), final, sum(early) / len(early)
