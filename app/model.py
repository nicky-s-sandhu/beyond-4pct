"""Back end for the dashboard: settings in, results out. No Dash or Plotly here.

Uses the project's vectorised engine (src/bengen/vec.py), which simulates all 69
historical 30-year retirements (1928-1996 starts) at once in a few milliseconds.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, vec  # noqa: E402

HORIZON = 30
LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"]

# The recommended plan from the write-up (output/decline/best, "Cuts <=5%, raises <=15%")
RECOMMENDED = {
    "rate": 6.1, "drift": -2.5, "floor": 75, "floor_mode": "fixed", "ceiling": 0.0,
    "band": 0.2, "cut_step": 5.0, "raise_step": 13.6,
    "stocks": 80, "intl": 28, "cash": 0, "threshold": 10, "max_years": 5, "refill_years": 5,
    "bonds": "intermediate", "intl_series": "intl", "who": "couple", "gamma": 3.0,
}
PRESETS = {
    "Recommended plan": RECOMMENDED,
    "Bengen 4% (50/50 US)": {**RECOMMENDED, "rate": 4.0, "drift": 0.0, "floor": 0, "band": 20.0, "cut_step": 0.0,
                             "raise_step": 0.0, "stocks": 50, "intl": 0},
    "Previous 8% plan": {**RECOMMENDED, "rate": 8.0, "drift": -0.5, "floor": 50, "floor_mode": "plan",
                         "ceiling": 2.0, "band": 20.0,
                         "cut_step": 30.0, "raise_step": 30.0, "stocks": 80, "intl": 25},
}
# UI values are in percent where natural. floor_mode "fixed": floor is a % of first-year spending, fixed in
# real terms; "plan": floor is a % of the planned (declining) path.


def to_params(s: dict) -> vec.Params:
    cash = s["cash"] / 100
    return vec.Params(
        rate=s["rate"] / 100, stocks=s["stocks"] / 100, intl=s["intl"] / 100, band=s["band"] / 100,
        cut_step=s["cut_step"] / 100, raise_step=s["raise_step"] / 100,
        floor=s["floor"] / 100, floor_flat=s.get("floor_mode", "fixed") == "fixed", ceiling=float(s["ceiling"]), drift=s["drift"] / 100,
        cash=min(cash, max(0.0, 1 - s["stocks"] / 100)), bucket=cash > 0, threshold=s["threshold"] / 100,
        max_years=int(s["max_years"]), refill_years=int(s["refill_years"]))


@lru_cache(maxsize=4)
def _frame(bonds: str, intl_series: str):
    df = data.load(intl_series=intl_series)
    if bonds == "intermediate":
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    return df


@lru_cache(maxsize=64)
def _windows(bonds: str, intl_series: str, intl: float):
    return vec.windows(_frame(bonds, intl_series), intl, HORIZON)


@dataclass
class Result:
    settings: dict
    params: vec.Params
    starts: list
    reals: np.ndarray          # (n, 30) real spending, $ per $100 start
    balance: np.ndarray        # (n, 30) real balance at year end, $ per $100 start
    plan: np.ndarray           # (30,) planned real spending
    floor: np.ndarray          # (30,) real floor, $ per $100 (zeros = none)
    ran_out: np.ndarray        # (n,) bool
    m: dict = field(default_factory=dict)


def run(settings: dict) -> Result:
    s = dict(settings)
    p = to_params(s)
    starts, S_r, B_r, C_r, infl = _windows(s["bonds"], s["intl_series"], round(p.intl, 4))
    out = vec.simulate(p, S_r, B_r, C_r, infl)
    bal = out["balances"]
    w = vec.survival_weights(HORIZON, who=s["who"])
    m = vec.metrics(p, out, gamma=float(s["gamma"]), weights=w)
    R = out["reals"] * 100
    ran = out["depleted"]
    drop_first = (1 - R / R[:, :1]).max(axis=1)
    drop_best = (1 - R / np.maximum.accumulate(R, axis=1)).max(axis=1)
    m.update({
        "big_drop_share": float(np.mean((drop_first >= 0.30) | ran)),
        "give_back_share": float(np.mean((drop_best >= 0.30) | ran)),
        "levels_best": _levels(drop_best, ran),
        "unluckiest": int(np.argmin((R * w).sum(axis=1))),
        "weights": w,
    })
    floor_path = (np.full(HORIZON, p.floor * p.rate * 100) if p.floor_flat else p.floor * p.plan(HORIZON) * 100) \
        if p.floor else np.zeros(HORIZON)
    return Result(s, p, list(starts), R, bal * 100, p.plan(HORIZON) * 100, floor_path, ran, m)


def _levels(cut, ran):
    return np.select([ran, cut >= 0.5 - 1e-9, cut >= 0.3, cut >= 0.15, cut >= 0.05],
                     ["Ran out", "Extreme", "Severe", "Moderate", "Mild"], "None")


def level_shares(levels) -> dict:
    return {lv: float(np.mean(levels == lv)) for lv in LEVELS}
