"""Treat the stock percentages in Pfau and Kitces's valuation-based allocation as parameters and optimise them.

Rule A (standalone): stock share = u when CAPE < lo x median, f when fair, o when CAPE > hi x median.
Rule B (glidepath + overlay): stock share moves from s0 to s1 over `years`, plus/minus `ov` points when CAPE is
cheap/expensive (unbounded, clipped to 0-100%).
Objective, as in the paper: SAFEMAX, the highest fixed real withdrawal rate that survived every 30-year retirement
(start-of-year withdrawals, annual rebalancing, Shiller data). Ties broken by median real wealth at 4%.

Honesty checks: (1) split sample, fit on 1881-1937 starts and test on 1938-1993 (and the reverse); (2) walk-forward:
each retirement starting in year Y uses settings chosen only from retirements already finished by Y (starts <= Y-30).

    python scripts/valuation_optimize.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import valuation as V  # noqa: E402

OUT = ROOT / "output" / "valuation"
D = V.load()
LAST = int(D.index.max()) - 29
ALL = list(range(1881, LAST + 1))
GRID = np.round(np.arange(0, 1.0001, 0.05), 2)
LOS, HIS = (0.5, 0.6, 2 / 3, 0.75, 0.85), (1.15, 1.25, 4 / 3, 1.5, 1.75)


class Data:
    def __init__(self, safe):
        S, B, rel = V.windows(D, ALL, safe=safe)
        self.S, self.B, self.rel, self.starts = S, B, rel, np.array(ALL)

    def sub(self, starts):
        k = np.isin(self.starts, starts)
        return self.S[k], self.B[k], self.rel[k]


def score(R):
    sm = V.safemax(R)
    return sm.min(), np.median(V.terminal_wealth(R))


def best_rule_a(S, B, rel, free_thresholds=True):
    """Grid search over (u, f, o[, lo, hi]); returns best settings by SAFEMAX then median wealth."""
    best = (-1, -1, None)
    for lo, hi in (itertools.product(LOS, HIS) if free_thresholds else [(2 / 3, 4 / 3)]):
        under, over = rel < lo, rel > hi
        fair = ~(under | over)
        # SAFEMAX is computed per (u, f, o); vectorise over the 21^3 grid in chunks of f
        for u in GRID:
            for o in GRID:
                w = np.where(under, u, np.where(over, o, 0.0))
                for f in GRID:
                    ww = w + fair * f
                    R = ww * S + (1 - ww) * B
                    sm = V.safemax(R).min()
                    if sm > best[0] + 1e-12:
                        best = (sm, None, dict(u=u, f=f, o=o, lo=lo, hi=hi))
    return best[0], best[2]


def apply_a(p, S, B, rel):
    w = np.where(rel < p["lo"], p["u"], np.where(rel > p["hi"], p["o"], p["f"]))
    return w * S + (1 - w) * B


def best_static(S, B):
    res = [(V.safemax(s * S + (1 - s) * B).min(), s) for s in GRID]
    return max(res)


def best_rule_b(S, B, rel):
    best = (-1, None)
    for s0, s1, yrs, ov in itertools.product(GRID[::2], GRID[::2], (10, 15, 20, 30), (0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)):
        p = dict(s0=s0, s1=s1, years=yrs, ov=ov)
        sm = V.safemax(apply_b(p, S, B, rel)).min()
        if sm > best[0] + 1e-12:
            best = (sm, p)
    return best


def apply_b(p, S, B, rel):
    st = V.Strategy(p["s0"], p["s1"], p["years"], overlay=p["ov"])
    return V.path_returns(st, S, B, rel)[0]


def walk_forward(data, kind):
    """SAFEMAX over test starts where each start's settings come only from retirements finished before it."""
    rates, used = [], []
    cache = {}
    for y in range(1941, LAST + 1):
        train = [s for s in ALL if s <= y - 30]
        key = len(train)
        if key not in cache:
            S, B, rel = data.sub(train)
            if kind == "static":
                cache[key] = ("static", best_static(S, B)[1])
            else:
                cache[key] = ("a", best_rule_a(S, B, rel, free_thresholds=False)[1])
        S, B, rel = data.sub([y])
        k, p = cache[key]
        R = (p * S + (1 - p) * B) if k == "static" else apply_a(p, S, B, rel)
        rates.append(V.safemax(R)[0]); used.append(p)
    return np.array(rates), used


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, notes = [], []
    for safe in ("bills", "bonds"):
        data = Data(safe)
        S, B, rel = data.S, data.B, data.rel
        sm_static, s_best = best_static(S, B)
        kp = V.Strategy(0.45, under=0.60, over=0.30)
        sm_kp = V.safemax(V.path_returns(kp, S, B, rel)[0]).min()
        sm_a_fixed, pa_fixed = best_rule_a(S, B, rel, free_thresholds=False)
        sm_a, pa = best_rule_a(S, B, rel)
        sm_b, pb = best_rule_b(S, B, rel)
        rows += [
            {"safe": safe, "rule": "Best static stock share", "settings": f"{s_best:.0%} stocks", "SAFEMAX %": sm_static * 100},
            {"safe": safe, "rule": "Pfau-Kitces 30/45/60", "settings": "60% cheap / 45% fair / 30% expensive", "SAFEMAX %": sm_kp * 100},
            {"safe": safe, "rule": "Optimised shares, 2/3 and 4/3 thresholds",
             "settings": f"{pa_fixed['u']:.0%} / {pa_fixed['f']:.0%} / {pa_fixed['o']:.0%}", "SAFEMAX %": sm_a_fixed * 100},
            {"safe": safe, "rule": "Optimised shares and thresholds",
             "settings": f"{pa['u']:.0%} / {pa['f']:.0%} / {pa['o']:.0%}, cheap < {pa['lo']:.2f}x, dear > {pa['hi']:.2f}x median",
             "SAFEMAX %": sm_a * 100},
            {"safe": safe, "rule": "Optimised glidepath + overlay",
             "settings": f"{pb['s0']:.0%}→{pb['s1']:.0%} over {pb['years']} yrs, ±{pb['ov']:.0%}", "SAFEMAX %": sm_b * 100},
        ]
        # split sample (fixed 2/3, 4/3 thresholds to keep it simple)
        for train, test in ((range(1881, 1938), range(1938, LAST + 1)), (range(1938, LAST + 1), range(1881, 1938))):
            Str, Btr, Rtr = data.sub(list(train)); Ste, Bte, Rte = data.sub(list(test))
            _, p = best_rule_a(Str, Btr, Rtr, free_thresholds=False)
            _, s = best_static(Str, Btr)
            notes.append({"safe": safe, "train": f"{train.start}-{train.stop - 1}", "test": f"{test.start}-{test.stop - 1}",
                          "optimised valuation rule": f"{p['u']:.0%}/{p['f']:.0%}/{p['o']:.0%}",
                          "its test SAFEMAX %": V.safemax(apply_a(p, Ste, Bte, Rte)).min() * 100,
                          "Pfau-Kitces 30/45/60 test %": V.safemax(V.path_returns(kp, Ste, Bte, Rte)[0]).min() * 100,
                          "static share fitted on train": f"{s:.0%}",
                          "static fitted, test SAFEMAX %": V.safemax(s * Ste + (1 - s) * Bte).min() * 100,
                          "fixed 60% test SAFEMAX %": V.safemax(0.6 * Ste + 0.4 * Bte).min() * 100})
        # walk-forward
        wf_a, used_a = walk_forward(data, "a")
        wf_s, used_s = walk_forward(data, "static")
        Ste, Bte, Rte = data.sub(list(range(1941, LAST + 1)))
        kp_t = V.safemax(V.path_returns(kp, Ste, Bte, Rte)[0])
        f60 = V.safemax(0.6 * Ste + 0.4 * Bte)
        notes.append({"safe": safe, "train": "walk-forward", "test": f"1941-{LAST}",
                      "optimised valuation rule": "re-fit each year", "its test SAFEMAX %": wf_a.min() * 100,
                      "Pfau-Kitces 30/45/60 test %": kp_t.min() * 100, "static share fitted on train": "re-fit each year",
                      "static fitted, test SAFEMAX %": wf_s.min() * 100, "fixed 60% test SAFEMAX %": f60.min() * 100})
        print(safe, "walk-forward settings used (first, last):", used_a[0], used_a[-1], "| static:", used_s[0], used_s[-1])
    a = pd.DataFrame(rows); b = pd.DataFrame(notes)
    a.to_csv(OUT / "optimised_in_sample.csv", index=False); b.to_csv(OUT / "optimised_out_of_sample.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_colwidth", 80, "display.precision", 2):
        print(f"\nIn sample: retirements starting 1881-{LAST}")
        print(a.to_string(index=False))
        print("\nOut of sample")
        print(b.to_string(index=False))


if __name__ == "__main__":
    main()
