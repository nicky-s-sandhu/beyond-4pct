"""Find the smoothest spending plan in each strategy family, under a pain limit.

Score: certainty-equivalent (CE) spending with constant relative risk aversion
gamma (default 3) over every retiree-year: the steady spending level a
risk-averse retiree would value the same as the whole uneven set of outcomes.
Cuts count for more than equal raises, so higher CE = more and smoother spending.
Years below $1 per $100 are scored as $1 (standing in for other income).

Hard limit: at most --max-extreme of retirees (default 10%, i.e. 6 of 69) may
have an extreme cut -- real spending 50%+ below the plan -- or run out.

Families (each optimised separately over its own parameters):
  Constant real      rate, stocks, intl, cash bucket (size, trigger, years, refill)
  Guardrails         rate, stocks, intl, band, cut size, raise size, floor, ceiling
  Guardrails + drift the above + planned real drift
  Everything         the above + cash bucket
Search: random sampling, then local refinement of the best candidates.
Robustness: each parameter nudged +/-10% of its range, plus random joint nudges.

    python scripts/smooth_optimize.py
    python scripts/smooth_optimize.py --gamma 5 --samples 6000
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, vec  # noqa: E402

OUT = ROOT / "output" / "smooth"

# parameter ranges (lo, hi); ints marked
RANGES = {
    "rate": (0.035, 0.10), "stocks": (0.3, 1.0), "intl": (0.0, 0.5), "band": (0.0, 0.4),
    "cut_step": (0.002, 0.35), "raise_step": (0.0, 0.35), "floor": (0.3, 1.0), "ceiling": (1.0, 3.0),
    "drift": (-0.015, 0.0), "cash": (0.0, 0.25), "threshold": (0.0, 0.3),
    "max_years": (1, 8), "refill_years": (1, 8),
}
INTS = {"max_years", "refill_years"}
FAMILIES = {
    "Constant real": ["rate", "stocks", "intl", "cash", "threshold", "max_years", "refill_years"],
    "Guardrails": ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "floor", "ceiling"],
    "Guardrails + drift": ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "floor", "ceiling",
                           "drift"],
    "Everything": ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "floor", "ceiling", "drift",
                   "cash", "threshold", "max_years", "refill_years"],
}
BASELINES = {
    "Bengen 4% (50/50 US)": vec.Params(rate=0.04, stocks=0.5),
    "Previous 8% plan": vec.Params(rate=0.08, stocks=0.8, intl=0.25, band=0.2, cut_step=0.3, raise_step=0.3,
                                   floor=0.5, ceiling=2.0, drift=-0.005),
}


class Evaluator:
    def __init__(self, df, gamma, max_extreme):
        self.df, self.gamma, self.max_extreme = df, gamma, max_extreme
        self.cache = {}

    def arrays(self, intl):
        key = round(intl, 4)
        if key not in self.cache:
            self.cache[key] = vec.windows(self.df, key)[1:]
        return self.cache[key]

    def __call__(self, p):
        out = vec.simulate(p, *self.arrays(p.intl))
        return vec.metrics(p, out, self.gamma)

    def score(self, m):
        excess = max(0.0, m["extreme_share"] - self.max_extreme)
        return m["ce"] - 100 * excess  # infeasible plans sink fast


def make(params: dict) -> vec.Params:
    p = vec.Params(**{k: v for k, v in params.items() if k in vec.Params.__dataclass_fields__})
    if p.stocks + p.cash > 1:
        p = replace(p, cash=max(0.0, 1 - p.stocks))
    if p.cash > 0.005 and "threshold" in params:
        p = replace(p, bucket=True)
    if p.cash <= 0.005:
        p = replace(p, cash=0.0, bucket=False)
    return p


def sample(names, rng):
    d = {}
    for k in names:
        lo, hi = RANGES[k]
        if k in INTS:
            d[k] = int(rng.integers(lo, hi + 1))
        elif k == "ceiling":
            d[k] = 0.0 if rng.random() < 0.3 else rng.uniform(lo, hi)
        elif k == "cash":
            d[k] = 0.0 if rng.random() < 0.3 else rng.uniform(lo, hi)
        else:
            d[k] = rng.uniform(lo, hi)
    return d


def nudge(d, names, rng, scale):
    e = dict(d)
    for k in names:
        lo, hi = RANGES[k]
        if k in INTS:
            if rng.random() < scale * 2:
                e[k] = int(np.clip(e[k] + rng.choice([-1, 1]), lo, hi))
        elif k in ("ceiling", "cash") and e[k] == 0.0:
            if rng.random() < scale:
                e[k] = rng.uniform(lo, hi) if k == "ceiling" else rng.uniform(0, 0.05)
        else:
            e[k] = float(np.clip(e[k] + rng.normal(0, scale * (hi - lo)), lo if k != "cash" else 0.0, hi))
    return e


NEUTRAL = {"band": 0.2, "cut_step": 0.002, "raise_step": 0.0, "floor": 1.0, "ceiling": 0.0, "drift": 0.0,
           "cash": 0.0, "threshold": 0.1, "max_years": 5, "refill_years": 5, "intl": 0.0}


def optimise(names, ev, samples, rng, refine_top=12, refine_iters=500, warm=()):
    pool = []
    for w in warm:  # best settings of smaller families, padded with neutral values
        d = {k: w.get(k, NEUTRAL.get(k)) for k in names}
        pool.append((ev.score(ev(make(d))), d))
    for _ in range(samples):
        d = sample(names, rng)
        m = ev(make(d))
        pool.append((ev.score(m), d))
    pool.sort(key=lambda t: -t[0])
    best = []
    for s0, d0 in pool[:refine_top]:
        cur, cur_s = d0, s0
        for it in range(refine_iters):
            scale = 0.08 * (1 - it / refine_iters) + 0.005
            cand = nudge(cur, names, rng, scale)
            s = ev.score(ev(make(cand)))
            if s > cur_s:
                cur, cur_s = cand, s
        best.append((cur_s, cur))
    best.sort(key=lambda t: -t[0])
    return best[0][1], pool


def robustness(d, names, ev, rng, n_joint=400):
    base = ev(make(d))
    rows = []
    for k in names:
        lo, hi = RANGES[k]
        for sgn in (-1, 1):
            if k in ("ceiling", "cash") and d[k] == 0.0:
                continue  # 0 means "none"; a nudge would invent a tiny cap or bucket
            e = dict(d)
            if k in INTS:
                e[k] = int(np.clip(e[k] + sgn, lo, hi))
            else:
                e[k] = float(np.clip(e[k] + sgn * 0.1 * (hi - lo), 0.0 if k in ("cash", "ceiling") else lo, hi))
            m = ev(make(e))
            rows.append({"param": k, "direction": "+" if sgn > 0 else "−", "value": e[k],
                         "ce_change": m["ce"] - base["ce"], "extreme_share": m["extreme_share"],
                         "feasible": m["extreme_share"] <= ev.max_extreme + 1e-12})
    joint = []
    for _ in range(n_joint):
        m = ev(make(nudge(d, names, rng, 0.05)))
        joint.append({"ce": m["ce"], "extreme_share": m["extreme_share"],
                      "feasible": m["extreme_share"] <= ev.max_extreme + 1e-12})
    return pd.DataFrame(rows), pd.DataFrame(joint)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gamma", type=float, default=3.0)
    ap.add_argument("--max-extreme", type=float, default=0.10)
    ap.add_argument("--samples", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--name", default="")
    ap.add_argument("--families", default=",".join(FAMILIES), help="comma-separated subset to optimise")
    ap.add_argument("--max-intl", type=float, default=None, help="cap the international share (0 = US only)")
    ap.add_argument("--intl-stress", action="store_true", help="use the pessimistic international series")
    a = ap.parse_args()
    if a.max_intl is not None:
        RANGES["intl"] = (0.0, a.max_intl)
    out = OUT / a.name if a.name else OUT
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    df = data.load(intl_series="intl_stress" if a.intl_stress else "intl")
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    n = len(vec.windows(df, 0.0)[0])
    max_extreme = np.floor(a.max_extreme * n + 1e-9) / n  # e.g. 6/69
    ev = Evaluator(df, a.gamma, max_extreme)

    results, chosen, robust, found = [], {}, {}, []
    for label, p in BASELINES.items():
        m = ev(p)
        results.append({"family": label, "kind": "baseline", **{k: v for k, v in m.items() if k != "levels"},
                        "params": json.dumps(p.as_dict())})
        chosen[label] = p
    for fam, names in FAMILIES.items():
        if fam not in a.families.split(","):
            continue
        d, _ = optimise(names, ev, a.samples, rng, warm=found)
        found.append(d)
        p = make(d)
        m = ev(p)
        results.append({"family": fam, "kind": "optimised", **{k: v for k, v in m.items() if k != "levels"},
                        "params": json.dumps(p.as_dict())})
        chosen[fam] = p
        r1, rj = robustness(d, names, ev, rng)
        r1["family"], rj["family"] = fam, fam
        robust[fam] = (r1, rj)
        print(f"{fam}: CE ${m['ce']:.2f}, extreme {m['extreme_share']:.0%}, typical yrs 1-10 "
              f"${m['typical_1_10']:.2f}", file=sys.stderr)

    res = pd.DataFrame(results)
    res.to_csv(out / "smooth_results.csv", index=False)
    pd.concat([r[0] for r in robust.values()]).to_csv(out / "robust_one_at_a_time.csv", index=False)
    pd.concat([r[1] for r in robust.values()]).to_csv(out / "robust_joint.csv", index=False)
    with open(out / "chosen_params.json", "w") as f:
        json.dump({k: v.as_dict() for k, v in chosen.items()}, f, indent=2)
    meta = {"gamma": a.gamma, "max_extreme": max_extreme, "samples": a.samples, "seed": a.seed, "n": n,
            "max_intl": RANGES["intl"][1], "intl_stress": a.intl_stress}
    with open(out / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(res.drop(columns="params").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
