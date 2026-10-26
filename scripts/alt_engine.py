"""Engine for comparing other withdrawal rules with the recommended plan.

One loop, all retirees at once (like src/bengen/vec.py, same timing: spending is set at
the start of each year from last year's balance, returns are earned, then the year's
spending is withdrawn at year end; the portfolio is rebalanced every year).

Spending rules (Rule.kind):
  "guard"  - the project's rule: planned real drift, +/-band guardrails on the withdrawal
             rate with separate cut and raise sizes, floor and cap.  Matches vec.simulate.
  "amort"  - amortisation (the VPW / ABW / TPAW family): each year the target is the level
             payment that would use up the portfolio by the planning horizon if it earned
             real return r, with payments tilted by drift.  Optional:
               cape_b > 0: r = r + cape_b * (1/CAPE - 1/17)  (valuation-aware return)
               max_cut / max_raise: limit each year's change vs last year's (smoothing)
               hyst > 0: leave spending alone while it is within +/-hyst of the target
                         (risk-based guardrail style), else move part way (back) to it.
               floor (share of year-1 spending, fixed real) and ceiling (x plan).
Any rule can use a glidepath for stocks: s0 -> s1 linearly over glide_years.
Optional: start rate set from valuations: rate = cape_a + cape_slope / CAPE at the start
(or, with cape_cap_only, valuations may only lower the start: min(rate, cape_a + cape_slope / CAPE)).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, vec  # noqa: E402

T = 30


@dataclass
class Rule:
    kind: str = "guard"
    rate: float = 0.04            # first-year rate (guard; also amort when start_from_rate)
    stocks: float = 0.5
    stocks_end: float | None = None
    glide_years: int = 0
    intl: float = 0.0
    drift: float = 0.0
    band: float = 0.2
    cut_step: float = 0.0
    raise_step: float = 0.0
    floor: float = 0.0            # share of year-1 spending, fixed in real terms
    ceiling: float = 0.0          # x plan
    # amortisation
    r: float = 0.03
    horizon: int = 30
    cape_b: float = 0.0
    max_cut: float = 1.0
    max_raise: float = 10.0
    hyst: float = 0.0
    back: float = 0.0
    # valuation-aware start (any rule): rate = cape_a + cape_slope / CAPE_0 when cape_slope > 0
    cape_a: float = 0.0
    cape_slope: float = 0.0
    cape_cap_only: bool = False   # True: valuations can only lower the start: min(rate, cape_a + slope/CAPE)

    def as_dict(self):
        return asdict(self)

    def stocks_path(self):
        if self.stocks_end is None or self.glide_years <= 0:
            return np.full(T + 1, self.stocks)
        f = np.clip(np.arange(T + 1) / self.glide_years, 0, 1)
        return self.stocks + (self.stocks_end - self.stocks) * f


def annuity_factor(r, n, g):
    """Spending per $1 today: level-growth (g) payments at the end of each of n years at real return r."""
    n = np.maximum(n, 1)
    k = np.arange(60)[None, :]
    disc = ((1 + g) ** k) / ((1 + np.asarray(r)[:, None]) ** (k + 1))
    disc = np.where(k < np.asarray(n)[:, None], disc, 0)
    return 1 / disc.sum(axis=1)


def simulate(rule: Rule, w: dict):
    """w: dict of arrays (n, T): S, B, C (nominal returns), I (inflation), cape (n, T) or None."""
    S_r, B_r, I = w["S"], w["B"], w["I"]
    n = S_r.shape[0]
    sp = rule.stocks_path()
    cape = w.get("cape")
    if rule.cape_slope > 0 and rule.cape_cap_only:
        rate0 = np.clip(np.minimum(rule.rate, rule.cape_a + rule.cape_slope / cape[:, 0]), 0.005, 0.15)
    elif rule.cape_slope > 0:
        rate0 = np.clip(rule.cape_a + rule.cape_slope / cape[:, 0], 0.005, 0.15)
    elif rule.kind == "amort" and rule.rate <= 0:
        r0 = rule.r + (rule.cape_b * (1 / cape[:, 0] - 1 / 17) if rule.cape_b > 0 else 0)
        rate0 = annuity_factor(np.full(n, 1.0) * r0, np.full(n, rule.horizon), rule.drift)
    else:
        rate0 = np.full(n, rule.rate)
    W = np.ones(n)
    price = np.ones(n)
    spend = rate0.copy()
    reals = np.empty((n, T))
    bal = np.empty((n, T))
    depleted = np.zeros(n, dtype=bool)
    hi_g, lo_g = rate0 * (1 + rule.band), rate0 * (1 - rule.band)
    planf = np.cumprod([1.0] + [1 + rule.drift] * (T - 1))
    for t in range(T):
        if t > 0:
            price = price * (1 + I[:, t - 1])
            prev = spend * (1 + I[:, t - 1]) * (1 + rule.drift)
            alive = W > 0
            if rule.kind == "guard":
                spend = prev
                if rule.cut_step > 0 or rule.raise_step > 0:
                    wr = np.where(alive, spend / np.where(alive, W, 1), np.inf)
                    spend = np.where(alive & (wr > hi_g), spend * (1 - rule.cut_step), spend)
                    spend = np.where(alive & (wr < lo_g), spend * (1 + rule.raise_step), spend)
            else:
                rr = rule.r + (rule.cape_b * (1 / cape[:, t] - 1 / 17) if rule.cape_b > 0 else 0)
                rr = np.full(n, 1.0) * rr
                target = W * annuity_factor(rr, np.full(n, rule.horizon - t), rule.drift)
                if rule.hyst > 0:
                    ratio = prev / np.maximum(target, 1e-12)
                    spend = np.where(ratio > 1 + rule.hyst, target * (1 + rule.hyst * rule.back),
                                     np.where(ratio < 1 - rule.hyst, target * (1 - rule.hyst * rule.back), prev))
                else:
                    spend = target
                spend = np.clip(spend, prev * (1 - rule.max_cut), prev * (1 + rule.max_raise))
            plan = rate0 * price * planf[t]
            if rule.floor > 0:
                spend = np.maximum(spend, rule.floor * rate0 * price)
            if rule.ceiling > 0:
                spend = np.minimum(spend, rule.ceiling * plan)
        s_now = sp[t]
        growth = s_now * S_r[:, t] + (1 - s_now) * B_r[:, t]
        W = W * (1 + growth)
        take = np.minimum(spend, np.maximum(W, 0))
        depleted |= take < spend - 1e-12
        W = W - take
        reals[:, t] = take / price
        bal[:, t] = W / (price * (1 + I[:, t]))
    return {"reals": reals, "depleted": depleted, "final": bal[:, -1], "balances": bal, "rate0": rate0,
            "planf": planf}


def metrics(rule: Rule, out, weights, gamma=3.0, subsistence=0.01):
    R = out["reals"]
    n = R.shape[0]
    plan = out["rate0"][:, None] * out["planf"][None, :]
    ran = out["depleted"]
    w = np.asarray(weights, float) / np.sum(weights)
    c = np.maximum(R, subsistence)
    ce = float(((c ** (1 - gamma)) * w).sum(axis=1).mean() ** (1 / (1 - gamma)))
    cut_plan = np.clip(1 - R / plan, 0, None).max(axis=1)
    rel = R / plan                                         # spending with the planned drift taken out
    give_back = (1 - rel / np.maximum.accumulate(rel, axis=1)).max(axis=1)   # unplanned give-back
    with np.errstate(divide="ignore", invalid="ignore"):
        yoy = np.nan_to_num(rel[:, 1:] / rel[:, :-1] - 1, nan=0.0, posinf=0.0, neginf=-1.0)
    lvl = np.select([ran, cut_plan >= 0.5 - 1e-9, cut_plan >= 0.3, cut_plan >= 0.15, cut_plan >= 0.05],
                    ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")
    gb_lvl = np.select([ran, give_back >= 0.5 - 1e-9, give_back >= 0.3, give_back >= 0.15, give_back >= 0.05],
                       ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")
    first = R[:, 0]
    return {
        "ce": ce * 100,
        "start": float(np.median(first)) * 100,
        "typical_1_10": float(np.median(R[:, :10].mean(axis=1))) * 100,
        "typical_11_20": float(np.median(R[:, 10:20].mean(axis=1))) * 100,
        "typical_21_30": float(np.median(R[:, 20:].mean(axis=1))) * 100,
        "worst_year": float(R.min()) * 100,
        "p10_year": float(np.percentile(R, 10)) * 100,
        "ran_out": int(ran.sum()),
        "extreme_share": float(np.mean((cut_plan >= 0.5 - 1e-9) | ran)),
        "severe_plus_share": float(np.mean((cut_plan >= 0.3) | ran)),
        "below_y1_30_share": float(np.mean(((1 - R / first[:, None]).max(axis=1) >= 0.3) | ran)),
        "giveback_30_share": float(np.mean((give_back >= 0.3) | ran)),
        "giveback_15_share": float(np.mean((give_back >= 0.15) | ran)),
        "giveback_median": float(np.median(give_back)),
        "cuts_5_per_retiree": float(np.mean((yoy < -0.05).sum(axis=1))),
        "yoy_sd": float(np.std(yoy)),
        "median_final": float(np.median(out["final"])) * 100,
        "n": n,
        "levels": lvl,
        "gb_levels": gb_lvl,
    }


# ---------------------------------------------------------------- data
def us_windows(intl: float, start_min=1928, start_max=1996, bonds="intermediate", intl_series="intl"):
    df = data.load(intl_series=intl_series)
    if bonds == "intermediate":
        df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    cape = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
    stocks = (1 - intl) * df.stocks + intl * df.intl if intl > 0 else df.stocks
    starts = [y for y in range(start_min, start_max + 1) if y + T - 1 <= df.index.max()]
    take = lambda s: np.array([s.loc[y:y + T - 1].values for y in starts])
    return {"starts": starts, "S": take(stocks), "B": take(df.bonds), "C": take(df.bills), "I": take(df.inflation),
            "cape": take(cape)}


def jst_frame(country: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "external" / "JSTdatasetR6.csv")
    x = d[d.country == country].set_index("year").sort_index()
    out = pd.DataFrame({"stocks": x.eq_tr, "bonds": 0.5 * x.bond_tr + 0.5 * x.bill_rate, "bills": x.bill_rate,
                        "inflation": x.cpi.pct_change()})
    return out


def jst_windows(country: str, start_min=1871, start_max=1991, cape=False):
    df = jst_frame(country)
    starts = []
    for y in range(start_min, start_max + 1):
        blk = df.loc[y:y + T - 1]
        if len(blk) == T and not blk.isna().any().any():
            starts.append(y)
    if not starts:
        return None
    take = lambda s: np.array([s.loc[y:y + T - 1].values for y in starts])
    w = {"starts": starts, "S": take(df.stocks), "B": take(df.bonds), "C": take(df.bills), "I": take(df.inflation)}
    if cape:
        c = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
        c = c.reindex(range(1871, 2030)).bfill()
        w["cape"] = take(c)
    return w


def evaluate(rule: Rule, w, weights, gamma=3.0):
    return metrics(rule, simulate(rule, w), weights, gamma)


def us_long_windows(intl: float):
    """US starts 1872-1996: JST data (US stocks only) for 1872-1927, project data from 1928."""
    a, b = jst_windows("USA", 1872, 1927, cape=True), us_windows(intl, 1928, 1996)
    return {"starts": a["starts"] + b["starts"], **{k: np.concatenate([a[k], b[k]]) for k in ("S", "B", "C", "I", "cape")}}
