"""Is there a better withdrawal experience than the recommended plan? Optimise strategies from the literature
on the same 69 historical retirements and compare.

Every family is tuned for the same score (certainty-equivalent spending, risk aversion 3, years weighted by
the chance a 65-year-old couple is alive) under the same protections the recommended plan gives:
  - at most 1 of 69 retirees runs out (the recommended plan: 1, the 1929 start)
  - 95% of retirees never spend below $4.575 per $100 (the recommended plan's floor: 75% of $6.10)
  - median real ending balance >= $50 per $100 (a reserve for living past 95; recommended: $87)
  - typical spending does not rise from one decade to the next (2% tolerance)
  - raises at most 15% a year, international at most 30% of stocks
Optional --smooth X adds: at most X of retirees ever fall 15%+ below their best year carried along the plan.

    python scripts/alt_optimize.py                 # all families
    python scripts/alt_optimize.py --smooth 0.5 --name smooth
    python scripts/alt_optimize.py --split         # tune on 1928-61 starts, test on 1962-96
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import alt, data, vec  # noqa: E402

OUT = ROOT / "output" / "alt"
REC = alt.Alt(kind="guard", stocks0=0.8, intl=0.28, rate=0.061, drift=-0.025, gband=0.002, cut_step=0.05,
              raise_step=0.136, floor=0.75)

# family: (base Alt, [(field, lo, hi)])
FAMILIES = {
    "Recommended rule, re-tuned": (REC, [("rate", .04, .08), ("drift", -.04, 0), ("gband", 0, .3),
                                         ("cut_step", .002, .05), ("raise_step", 0, .15), ("stocks0", .3, 1),
                                         ("intl", 0, .3)]),
    "Recommended rule + rising-equity glidepath": (
        replace(REC, stocks1=0.8), [("rate", .04, .08), ("drift", -.04, 0), ("gband", 0, .3),
                                    ("cut_step", .002, .05), ("raise_step", 0, .15), ("stocks0", .2, 1),
                                    ("stocks1", .3, 1), ("glide_years", 1, 20), ("intl", 0, .3)]),
    "Amortization (ABW/TPAW-style), smoothed": (
        alt.Alt(kind="amort", r_bond=0.01), [("stocks0", .3, 1), ("intl", 0, .3), ("r_stock", 0, .08),
                                             ("horizon", 30, 45), ("tilt", -.04, 0), ("band", 0, .2),
                                             ("adjust", .1, 1), ("max_cut", .01, .3), ("max_raise", 0, .15),
                                             ("floor", 0, .9)]),
    "CAPE-aware amortization, smoothed": (
        alt.Alt(kind="cape", r_bond=0.01), [("stocks0", .3, 1), ("intl", 0, .3), ("cape_a", -.03, .04),
                                            ("cape_b", 0, 1.5), ("horizon", 30, 45), ("tilt", -.04, 0),
                                            ("band", 0, .2), ("adjust", .1, 1), ("max_cut", .01, .3),
                                            ("max_raise", 0, .15), ("floor", 0, .9)]),
    "Percent of portfolio with limits (Vanguard dynamic)": (
        alt.Alt(kind="pct"), [("pct", .03, .09), ("stocks0", .3, 1), ("intl", 0, .3), ("tilt", -.04, 0),
                              ("band", 0, .2), ("adjust", .1, 1), ("max_cut", .01, .3), ("max_raise", 0, .15),
                              ("floor", 0, .9)]),
    "TIPS-ladder floor + stock upside": (
        alt.Alt(kind="amort", ladder_yield=0.015, r_bond=0.01), [("ladder", 0, .045), ("stocks0", .3, 1),
                                                                ("intl", 0, .3), ("r_stock", 0, .08),
                                                                ("horizon", 30, 45), ("tilt", -.04, 0),
                                                                ("band", 0, .2), ("adjust", .1, 1),
                                                                ("max_cut", .01, .3), ("max_raise", 0, .15)]),
}
INTS = {"horizon", "glide_years"}
BASELINES = {
    "Recommended plan": REC,
    "Bengen 4% (50/50 US)": alt.Alt(kind="guard", stocks0=0.5, rate=0.04),
    "Vanguard dynamic, published (5%, +5%/-2.5%)": alt.Alt(kind="pct", pct=0.05, stocks0=0.5, intl=0.3,
                                                            max_raise=0.05, max_cut=0.025),
    "ERN CAPE rule (1.75% + 0.5/CAPE), 75/25": alt.Alt(kind="capepct", stocks0=0.75, cape_a=0.0175, cape_b=0.5),
}


class Data:
    def __init__(self, bonds="intermediate", intl_series="intl", horizon=30, starts=None):
        df = data.load(intl_series=intl_series)
        if bonds == "intermediate":
            df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
        cape = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
        st = list(range(df.index.min(), df.index.max() - horizon + 2))
        if starts is not None:
            st = [y for y in st if starts[0] <= y <= starts[1]]
        take = lambda s: np.array([s.loc[y:y + horizon - 1].values for y in st])
        self.starts = st
        self.US, self.INTL = take(df["stocks"]), take(df["intl"])
        self.B, self.I, self.K = take(df["bonds"]), take(df["inflation"]), take(cape)
        self.w = vec.survival_weights(horizon, who="couple")

    def run(self, a: alt.Alt):
        S = (1 - a.intl) * self.US + a.intl * self.INTL
        out = alt.simulate(a, S, self.B, self.I, self.K)
        return out, alt.metrics(out, tilt=a.drift if a.kind == "guard" else a.tilt, weights=self.w)


def violations(m, smooth=None, p5=4.575, legacy=50.0, protect=False):
    v = 0.0
    v += max(0, m["ran_out"] - 1) * 1.0
    v += max(0, p5 - m["p5_low"]) * 2.0
    v += max(0, legacy - m["median_final"]) / 20
    v += max(0, m["typical_11_20"] - 1.02 * m["typical_1_10"]) + max(0, m["typical_21_30"] - 1.02 * m["typical_11_20"])
    if smooth is not None:
        v += max(0, m["giveback15"] - smooth) * 10
    if protect:  # the recommended plan's smoothness: no unplanned one-year cut of 10%+, and at most
        # 31% of retirees ever 30%+ below their best year carried along the plan
        v += max(0, m["cut10_share"] - 0.015) * 10 + max(0, m["giveback30"] - 0.31) * 10
    return v


def violations_boot(m, n, max_out=0.05, legacy=50.0, max_below=None, below=3.9):
    """Constraints for tuning on bootstrapped (out-of-history) retirements."""
    v = max(0, m["ran_out"] / n - max_out) * 20
    if max_below is not None:
        v += max(0, float(np.mean(m["low"] < below)) - max_below) * 20
    v += max(0, legacy - m["median_final"]) / 20
    v += max(0, m["typical_11_20"] - 1.02 * m["typical_1_10"]) + max(0, m["typical_21_30"] - 1.02 * m["typical_11_20"])
    v += max(0, m["cut10_share"] - m["ran_out"] / n - 0.05) * 10 + max(0, m["giveback30"] - 0.31) * 10
    return v


def build(base, spec, x):
    kw = {}
    for (f, lo, hi), xi in zip(spec, x):
        kw[f] = int(round(xi)) if f in INTS else float(xi)
    return replace(base, **kw)


def optimise(D, base, spec, smooth=None, seed=1, maxiter=250, legacy=50.0, protect=False, boot=False, popsize=20,
             max_below=None):
    def f(x):
        a = build(base, spec, x)
        _, m = D.run(a)
        if boot:
            return -m["ce"] + 50 * violations_boot(m, len(D.starts), legacy=legacy, max_below=max_below)
        return -m["ce"] + 50 * violations(m, smooth, legacy=legacy, protect=protect)
    bounds = [(lo, hi) for _, lo, hi in spec]
    # start from the base strategy's own values (so a re-tune can never end below the recommended plan)
    x0 = [min(max(getattr(base, f_) if getattr(base, f_) is not None else lo, lo), hi) for f_, lo, hi in spec]
    r = differential_evolution(f, bounds, seed=seed, maxiter=maxiter, popsize=popsize, tol=1e-7, polish=False,
                               mutation=(0.5, 1.0), recombination=0.8, init="sobol", x0=x0)
    # local polish with Nelder-Mead inside bounds
    from scipy.optimize import minimize
    lo = np.array([b[0] for b in bounds]); hi = np.array([b[1] for b in bounds])
    p = minimize(lambda x: f(np.clip(x, lo, hi)), r.x, method="Nelder-Mead",
                 options={"maxiter": 600 if boot else 3000, "xatol": 1e-5, "fatol": 1e-6})
    x = np.clip(p.x if p.fun < r.fun else r.x, lo, hi)
    return build(base, spec, x)


def row(name, a, m):
    keep = ["ce", "ran_out", "first_year", "typical_1_10", "typical_11_20", "typical_21_30", "lifetime_median",
            "worst_low", "p5_low", "p10_low", "median_low", "giveback15", "giveback30", "cut10_share", "cut_years",
            "median_final", "p10_final"]
    return {"strategy": name, **{k: m[k] for k in keep}, "params": {k: v for k, v in a.as_dict().items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smooth", type=float, default=None)
    ap.add_argument("--legacy", type=float, default=50.0)
    ap.add_argument("--families", default="")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--maxiter", type=int, default=250)
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--protect", action="store_true", help="also match the recommended plan's smoothness")
    ap.add_argument("--boot", type=int, default=0, help="tune on this many bootstrapped retirements instead")
    ap.add_argument("--max-below", type=float, default=None, help="(boot) max share ever spending < $3.90")
    ap.add_argument("--name", default="main")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fams = [f for f in a.families.split("|") if f] or list(FAMILIES)
    D = Data()
    rows = []
    for name, b in BASELINES.items():
        out, m = D.run(b)
        rows.append(row(name, b, m))
    if a.split:
        Dtr, Dte = Data(starts=(1928, 1961)), Data(starts=(1962, 1996))
    for fam in fams:
        t0 = time.time()
        base, spec = FAMILIES[fam]
        if a.boot:
            import alt_robust as ar
            Db = ar.bootstrap(n=a.boot, seed=11)
            best = optimise(Db, base, spec, seed=a.seed, maxiter=a.maxiter, legacy=a.legacy, boot=True, popsize=12,
                            max_below=a.max_below)
        else:
            best = optimise(Dtr if a.split else D, base, spec, a.smooth, a.seed, a.maxiter, a.legacy, a.protect)
        out, m = D.run(best)
        r = row(fam, best, m)
        r["violation"] = violations(m, a.smooth, legacy=a.legacy, protect=a.protect)
        if a.boot:
            mb = Db.run(best)[1]
            r["boot_train"] = {k: v for k, v in mb.items() if not isinstance(v, np.ndarray)}
            r["violation"] = violations_boot(mb, a.boot, legacy=a.legacy, max_below=a.max_below)
        if a.split:
            r["train"] = Dtr.run(best)[1]["ce"]
            r["test"] = Dte.run(best)[1]["ce"]
            r["test_metrics"] = {k: v for k, v in Dte.run(best)[1].items() if not isinstance(v, np.ndarray)}
        rows.append(r)
        print(f"{fam}: CE {m['ce']:.3f}  viol {r['violation']:.4f}  ({time.time()-t0:.0f}s)", flush=True)
    (OUT / f"{a.name}.json").write_text(json.dumps(rows, indent=1, default=float))
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("params", "test_metrics")} for r in rows])
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.precision", 3):
        print(df.set_index("strategy"))


if __name__ == "__main__":
    main()
