"""The survey's four tests, inside the recommended withdrawal plan.

Portfolios (stocks are 70% US / 30% international; bonds are half T-bills, half 10-year Treasuries):
  baseline     fixed 80% stocks
  ECY          Shiller-ECY rule: 80% normal, +/-12.5 points per point of ECY vs its median, 50-100%
  gold         a 10% gold sleeve (Damodaran's gold series), taken from stocks or from bonds
  trend        a 10% or 20% trend-following sleeve (data/raw/trend_proxy.csv), taken from bonds or pro rata
  combos       ECY with the best sleeves
A sleeve funded "pro rata" scales the stock/bond mix by (1 - sleeve).

For each portfolio the plan's spending settings (floor, band, cut, raise; cap kept at 1.10x) are retuned on a grid, the starting
rate set so 2% of reshuffled retirements run out, and the best smooth-spending score kept. Reshuffled history is
drawn from 1928-2020 (the trend proxy ends in 2020). Split test: spending settings tuned on years 1928-1974 only,
then the rate re-solved and the portfolio scored on years 1975-2020 only, and the other way round.
Outputs output/etf_tests/*.csv
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]
from bengen import alt, vec, stockrule as sr          # noqa: E402
import valuation_best as vb                           # noqa: E402

OUT = ROOT / "output" / "etf_tests"
OUT.mkdir(parents=True, exist_ok=True)
P0 = vb.P
WTS = vb.WTS
ECY = sr.Rule("ecys", 0.8, 1, 1.0, 0.5)
FIX80 = sr.Rule("none", 0.8)

# (name, stock rule, gold share, trend share, funding)
PORTS = [
    ("Fixed 80% (plan)", FIX80, 0.0, 0.0, "-"),
    ("ECY rule", ECY, 0.0, 0.0, "-"),
    ("80/20 + 10% gold from stocks", FIX80, 0.10, 0.0, "stocks"),
    ("80/20 + 10% gold from bonds", FIX80, 0.10, 0.0, "bonds"),
    ("80/20 + 10% trend from bonds", FIX80, 0.0, 0.10, "bonds"),
    ("80/20 + 20% trend from bonds", FIX80, 0.0, 0.20, "bonds"),
    ("80/20 + 20% trend pro rata", FIX80, 0.0, 0.20, "pro rata"),
    ("ECY + 10% gold pro rata", ECY, 0.10, 0.0, "pro rata"),
    ("ECY + 20% trend pro rata", ECY, 0.0, 0.20, "pro rata"),
    ("ECY + 10% gold + 10% trend pro rata", ECY, 0.10, 0.10, "pro rata"),
]
# the 1.10x spending cap stays fixed (spending never more than 10% above plan, as chosen for the plan)
GRID = dict(floor=(0.35, 0.42, 0.50), band=(0.08, 0.12, 0.16, 0.22), cut_step=(0.085, 0.12, 0.16),
            raise_step=(0.15, 0.25, 0.40))


def frame(end=2020):
    df = vb.frame("plan").loc[:end].copy()
    dam = pd.read_csv(ROOT / "data/raw/damodaran_returns.csv").set_index("year")
    df["gold"] = dam["gold"].reindex(df.index) / 100
    tr = pd.read_csv(ROOT / "data/raw/trend_proxy.csv").set_index("year")["trend"]
    df["trend"] = tr.reindex(df.index)
    return df


class Set(vb.Set):
    def __init__(self, df, idx):
        super().__init__(df, idx)
        self.G = df["gold"].values[idx]
        self.T = df["trend"].fillna(0).values[idx]


def boot(df, years=None):
    d = df if years is None else df.loc[years[0]:years[1]]
    return Set(d, alt.bootstrap_index(len(d), vb.N, 30, vb.BLOCK, vb.SEED))


def returns(port, st: Set):
    _, rule, g, t, fund = port
    W = sr.shares(rule, st.X[rule.signal])
    if fund == "stocks":
        Ws, Wb = W - g - t, 1 - W
    elif fund == "bonds":
        Ws, Wb = W, 1 - W - g - t
    else:                                   # pro rata, or no sleeve
        Ws, Wb = (1 - g - t) * W, (1 - g - t) * (1 - W)
    R = Ws * st.S + Wb * st.B + g * st.G + t * st.T
    return R, Ws


def evaluate(p, R, st, rate=None):
    one, zero = np.ones_like(R), np.zeros_like(R)
    r = sr.rate_at(p, one, R, zero, st.I) if rate is None else rate
    pr = replace(p, rate=r)
    out = sr.simulate(pr, one, R, zero, st.I)
    m = vec.metrics(pr, out, weights=WTS)
    return {"rate": r * 100, "ce": m["ce"], "ran_out": out["depleted"].mean() * 100, "typ_1_10": m["typical_1_10"],
            "typ_avg": m["typical_avg"], "p10_year": m["p10_year"], "cut30": m["severe_plus_share"] * 100,
            "median_final": m["median_final"]}


def tune(port, st):
    R, _ = returns(port, st)
    best = None
    for vals in itertools.product(*GRID.values()):
        p = replace(P0, **dict(zip(GRID, vals)))
        e = evaluate(p, R, st)
        if best is None or e["ce"] > best[1]["ce"]:
            best = (p, e)
    return best


def settings(p):
    return {k: getattr(p, k) for k in GRID}


def main():
    df = frame()
    full = boot(df)
    early, late = boot(df, (1928, 1974)), boot(df, (1975, 2020))
    rows, split = [], []
    for port in PORTS:
        name = port[0]
        R, Ws = returns(port, full)
        plan = evaluate(P0, R, full)                        # with today's plan settings, rate re-solved
        p, tuned = tune(port, full)
        r_ann = (1 + R).prod(axis=1) ** (1 / 30) - 1
        real = (1 + R) / (1 + full.I) - 1
        dd = np.minimum.accumulate(np.cumprod(1 + real, axis=1) / np.maximum.accumulate(np.cumprod(1 + real, axis=1), axis=1), axis=1)[:, -1]
        rows.append({"portfolio": name, "plan_rate": plan["rate"], "plan_ce": plan["ce"],
                     **{f"tuned_{k}": v for k, v in tuned.items()}, **settings(p),
                     "avg_stocks": Ws.mean() * 100, "median_real_return": np.median((1 + real).prod(axis=1) ** (1 / 30) - 1) * 100,
                     "median_worst_drawdown": np.median(1 - dd) * 100})
        for fit, test, fn, tn in ((early, late, "1928-74", "1975-2020"), (late, early, "1975-2020", "1928-74")):
            pf, ins = tune(port, fit)
            Rt, _ = returns(port, test)
            oos = evaluate(pf, Rt, test)
            split.append({"portfolio": name, "fit": fn, "test": tn, "rate_in": ins["rate"], "ce_in": ins["ce"],
                          "rate_out": oos["rate"], "ce_out": oos["ce"]})
        print(name, f"plan {plan['rate']:.2f}/{plan['ce']:.2f}", f"tuned {tuned['rate']:.2f}/{tuned['ce']:.2f}",
              settings(p), "split out", [round(s['rate_out'], 2) for s in split[-2:]], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "results.csv", index=False)
    pd.DataFrame(split).to_csv(OUT / "split.csv", index=False)

    # check without the trend proxy: 1928-2025 for the portfolios that don't need it
    df25 = frame(2025)
    full25 = boot(df25)
    chk = []
    for port in PORTS:
        if port[3] > 0:
            continue
        p, e = tune(port, full25)
        chk.append({"portfolio": port[0], **e, **settings(p)})
    pd.DataFrame(chk).to_csv(OUT / "results_1928_2025.csv", index=False)
    print(pd.DataFrame(chk)[["portfolio", "rate", "ce", "ran_out"]].round(2))
    hist = df[["S", "bonds", "gold", "trend"]].loc[1928:2020]
    print("correlations 1928-2020\n", hist.corr().round(2))


if __name__ == "__main__":
    main()
