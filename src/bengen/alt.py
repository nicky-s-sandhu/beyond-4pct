"""Alternative withdrawal strategies from the literature, on the same historical windows as vec.py.

Same timing as vec.simulate: spending is set at the start of each year in real (start-of-year)
dollars and withdrawn at the end of the year after that year's returns; annual rebalancing.

Spending rules (Alt.kind):
  guard  - the project's rule (vec.py): planned real drift, +/-band guardrails on the withdrawal
           rate with fixed cut/raise sizes, floor as a share of first-year spending.
  amort  - amortisation-based withdrawal (ABW / VPW / TPAW family): each year spend the level
           payment that would exhaust the portfolio over the remaining horizon at an assumed real
           return, with spending planned to change by `tilt` per year.
  cape   - as amort, but the assumed real stock return is cape_a + cape_b / CAPE (ERN's rule:
           cape_a = 0, cape_b = 1 means "expect the cyclically adjusted earnings yield").
  capepct- withdraw (cape_a + cape_b / CAPE) of the current portfolio (ERN's CAPE-based rule).
  pct    - a fixed percentage of the current portfolio (Vanguard's dynamic spending rule when
           combined with max_raise / max_cut limits on year-over-year changes).

Smoothing (amort/cape/pct), in the spirit of risk-based guardrails: keep last year's real spending
(moved along the tilt) unless the rule's target differs from it by more than `band`; then close
`adjust` of the gap, limited to max_cut / max_raise in one year. Optional floor (share of year-1
spending, fixed in real terms).

Floor-and-upside: `ladder` buys a 30-year inflation-indexed (TIPS-style) ladder paying `ladder`
real dollars a year per $1 started, priced at real yield `ladder_yield`; the rest is invested and
spent with the rule above. Historical TIPS did not exist before 1997, so the yield is an assumption.

Glidepath: stock share moves linearly from stocks0 to stocks1 over glide_years (rising-equity
"bond tent" when stocks1 > stocks0).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace

import numpy as np


@dataclass
class Alt:
    kind: str = "amort"
    stocks0: float = 0.6
    stocks1: float | None = None   # None = constant stocks0
    glide_years: int = 10
    intl: float = 0.0
    # guard rule
    rate: float = 0.04
    drift: float = 0.0
    curve: str = ""                # "blanchett": planned real change by age from Blanchett (2014), replaces drift
    start_age: int = 65
    expenditure: float = 75000.0   # household spending ($/yr) for Blanchett's equation
    gband: float = 0.2
    cut_step: float = 0.0
    raise_step: float = 0.0
    # amort / cape / pct target
    r_stock: float = 0.05
    r_bond: float = 0.01
    cape_a: float = 0.0
    cape_b: float = 1.0
    pct: float = 0.05
    horizon: int = 30
    tilt: float = 0.0
    # smoothing (amort/cape/pct)
    band: float = 0.0
    adjust: float = 1.0
    max_cut: float = 1.0
    max_raise: float = 1.0
    floor: float = 0.0             # share of year-1 total spending, fixed real (all kinds)
    # floor-and-upside
    ladder: float = 0.0
    ladder_yield: float = 0.015

    def as_dict(self):
        return asdict(self)

    def drifts(self, T):
        """Planned real change applied going into each year (index 0 unused)."""
        if self.curve == "blanchett":
            return np.array([0.0] + [blanchett_change(self.start_age + t - 1, self.expenditure) for t in range(1, T)])
        return np.array([0.0] + [self.drift] * (T - 1))

    def stock_path(self, T):
        if self.stocks1 is None:
            return np.full(T, self.stocks0)
        g = max(int(self.glide_years), 1)
        f = np.clip(np.arange(T) / g, 0, 1)
        return self.stocks0 + (self.stocks1 - self.stocks0) * f

    def ladder_cost(self, T=30):
        y = self.ladder_yield
        return self.ladder * float(np.sum((1 + y) ** -np.arange(1, T + 1)))


def blanchett_change(age, expenditure=75000.0):
    """Real change in spending from `age` to age + 1: Blanchett (2014), 'Exploring the Retirement Consumption
    Puzzle', Journal of Financial Planning 27(5), equation 1. Averages about -1%/yr from 65 to 95, smallest
    at the start and end of retirement (the 'spending smile'), steepest around age 78."""
    return 0.00008 * age ** 2 - 0.0125 * age - 0.00661 * np.log(expenditure) + 0.546


def _annuity(r, g, n):
    """Present value at start of year of end-of-year payments 1, (1+g), ... for n years at return r."""
    n = np.maximum(n, 1)
    q = (1 + g) / (1 + r)
    with np.errstate(divide="ignore", invalid="ignore"):
        pv = np.where(np.abs(q - 1) < 1e-9, n, (1 - q ** n) / (1 - q)) / (1 + r)
    return pv


def simulate(a: Alt, S_r, B_r, infl, cape=None):
    """S_r, B_r, infl: (n, T) nominal returns and inflation; cape: (n, T) CAPE at the start of each year.
    Returns dict like vec.simulate: reals (n, T) per $1 start, depleted, final, balances."""
    n, T = S_r.shape
    s_path = a.stock_path(T)
    L = a.ladder_cost(T) if a.ladder > 0 else 0.0
    W = np.full(n, 1.0 - L)                 # invested portfolio, nominal
    price = np.ones(n)                      # start-of-year price level
    reals = np.empty((n, T))
    balances = np.empty((n, T))
    depleted = np.zeros(n, dtype=bool)
    prev = np.zeros(n)                      # last year's total real spending
    first = None
    hi_g, lo_g = a.rate * (1 + a.gband), a.rate * (1 - a.gband)
    dr = a.drifts(T)
    for t in range(T):
        if t > 0:
            price = price * (1 + infl[:, t - 1])
        s = s_path[t]
        w_real = W / price
        ladder_inc = a.ladder if (a.ladder > 0) else 0.0
        if a.kind == "guard":
            if t == 0:
                spend = np.full(n, a.rate)
            else:
                spend = prev * (1 + dr[t])
                if a.cut_step > 0 or a.raise_step > 0:
                    with np.errstate(divide="ignore", invalid="ignore"):
                        wr = np.where(w_real > 0, spend / np.where(w_real > 0, w_real, 1), np.inf)
                    alive = w_real > 0
                    spend = np.where(alive & (wr > hi_g), spend * (1 - a.cut_step), spend)
                    spend = np.where(alive & (wr < lo_g), spend * (1 + a.raise_step), spend)
            port_spend = spend
            total = port_spend + ladder_inc
        else:
            if a.kind == "pct":
                target = a.pct * w_real
            elif a.kind == "capepct":
                target = (a.cape_a + a.cape_b / cape[:, t]) * w_real
            else:
                if a.kind == "cape":
                    rs = a.cape_a + a.cape_b / cape[:, t]
                else:
                    rs = np.full(n, a.r_stock)
                r = s * rs + (1 - s) * a.r_bond
                target = w_real / _annuity(r, a.tilt, a.horizon - t)
            target = np.maximum(target, 0.0) + ladder_inc
            if t == 0:
                total = target
            else:
                base = prev * (1 + a.tilt)
                gap = np.where(base > 0, target / np.where(base > 0, base, 1) - 1, 0.0)
                move = np.where(np.abs(gap) > a.band, a.adjust * gap, 0.0)
                move = np.clip(move, -a.max_cut, a.max_raise)
                total = base * (1 + move)
        if t == 0:
            first = total.copy()
        if a.floor > 0:
            total = np.maximum(total, a.floor * first)
        port_spend = np.maximum(total - ladder_inc, 0.0)
        # returns, then end-of-year withdrawal (nominal, in start-of-year prices as in vec.py)
        W = W * (1 + s * S_r[:, t] + (1 - s) * B_r[:, t])
        want = port_spend * price
        take = np.minimum(want, np.maximum(W, 0.0))
        depleted |= take < want - 1e-12
        W = W - take
        reals[:, t] = take / price + ladder_inc
        prev = np.where(take < want - 1e-12, take / price + ladder_inc, total)
        balances[:, t] = W / (price * (1 + infl[:, t]))
    final = W / (price * (1 + infl[:, T - 1]))
    return {"reals": reals, "depleted": depleted, "final": final, "balances": balances}


def stock_returns(df, intl):
    return (1 - intl) * df["stocks"] + intl * df["intl"] if intl > 0 else df["stocks"]


def windows(df, cape_s, intl, horizon=30):
    starts = list(range(df.index.min(), df.index.max() - horizon + 2))
    take = lambda s: np.array([s.loc[y:y + horizon - 1].values for y in starts])
    return starts, take(stock_returns(df, intl)), take(df["bonds"]), take(df["inflation"]), take(cape_s)


def metrics(out, tilt=0.0, gamma=3.0, weights=None, subsistence=0.01):
    """Plan-free experience measures, $ per $100 started."""
    R = out["reals"]
    n, T = R.shape
    w = np.ones(T) if weights is None else np.asarray(weights, float)
    w = w / w.sum()
    c = np.maximum(R, subsistence)
    ce = float(((c ** (1 - gamma)) * w).sum(axis=1).mean() ** (1 / (1 - gamma)))
    ran = out["depleted"]
    low = np.where(ran, 0.0, R.min(axis=1))
    # unplanned give-back: shortfall versus the best year carried forward along the planned tilt
    path = np.cumprod(1 + np.asarray(tilt, float)) if np.ndim(tilt) else (1 + tilt) ** np.arange(T)
    adj = R / path
    best = np.maximum.accumulate(adj, axis=1)
    giveback = (1 - adj / best).max(axis=1)
    yoy = R[:, 1:] / np.where(R[:, :-1] > 0, R[:, :-1], 1) - 1
    unpl = yoy - (np.asarray(tilt, float)[1:] if np.ndim(tilt) else tilt)
    return {
        "ce": ce * 100,
        "ran_out": int(ran.sum()),
        "first_year": float(np.median(R[:, 0])) * 100,
        "typical_1_10": float(np.median(R[:, :10].mean(axis=1))) * 100,
        "typical_11_20": float(np.median(R[:, 10:20].mean(axis=1))) * 100,
        "typical_21_30": float(np.median(R[:, 20:].mean(axis=1))) * 100,
        "lifetime_median": float(np.median(R.mean(axis=1))) * 100,
        "worst_low": float(low.min()) * 100,
        "p5_low": float(np.percentile(low, 5)) * 100,
        "p10_low": float(np.percentile(low, 10)) * 100,
        "median_low": float(np.median(low)) * 100,
        "giveback30": float(np.mean((giveback >= 0.30) | ran)),
        "giveback15": float(np.mean((giveback >= 0.15) | ran)),
        "cut10_share": float(np.mean((unpl <= -0.10).any(axis=1) | ran)),
        "cut_years": float((unpl <= -0.02).sum(axis=1).mean()),
        "median_final": float(np.median(out["final"])) * 100,
        "p10_final": float(np.percentile(out["final"], 10)) * 100,
        "low": low * 100,
        "giveback": giveback,
    }
