"""Smooth spending that follows a retirement spending smile (more early, less later).

Builds on smooth_optimize.py with three changes:
  * The plan declines in three phases (years 1-10, 11-20, 21-30); the optimiser
    picks each decade's real change in [-3%, 0%]. Cuts are measured against this
    plan, so a planned decline is not counted as pain.
  * The score weights each year by the chance that at least one of a 65-year-old
    couple is alive (SSA 2022 period life table), so early spending counts more.
  * International stocks are capped at 30% of the stock allocation.
Hard limits: at most 10% of retirees cut 50%+ below plan or run out, and the typical
(median) retiree's spending must not rise from one decade to the next.

    python scripts/smile_optimize.py
    python scripts/smile_optimize.py --who single --name single
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
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import data, vec  # noqa: E402
import smooth_optimize as so  # noqa: E402

OUT = ROOT / "output" / "smile"
so.RANGES.update({"intl": (0.0, 0.30), "drift": (-0.03, 0.0), "drift2": (-0.03, 0.0), "drift3": (-0.03, 0.0)})
so.NEUTRAL.update({"drift2": 0.0, "drift3": 0.0})
ADJ = ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "floor", "ceiling", "drift", "drift2", "drift3"]
BUCKET = ["cash", "threshold", "max_years", "refill_years"]
# name -> (parameters searched, range overrides)
SMILE_FAMILIES = {
    "Smile, fixed spending": (["rate", "stocks", "intl", "drift", "drift2", "drift3"] + BUCKET, {}),
    "Smile + tiny adjustments (cuts <=2%)": (ADJ, {"cut_step": (0.002, 0.02)}),
    "Smile + tiny adjustments (cuts <=5%)": (ADJ, {"cut_step": (0.002, 0.05)}),
    "Smile + tiny both ways (cuts and raises <=5%)": (ADJ, {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.05)}),
    "Smile + tiny adjustments + cash (cuts <=5%)": (ADJ + BUCKET, {"cut_step": (0.002, 0.05)}),
    "Smile + any-size guardrails": (ADJ, {}),
}
ADJ_M = [k for k in ADJ if k != "drift3"]  # mirror smile: years 21-30 rise at -drift2
MIRROR_FAMILIES = {
    "Mirror smile, fixed spending": (["rate", "stocks", "intl", "drift", "drift2"] + BUCKET, {}),
    "Mirror smile, cuts <=5%, raises <=10%": (ADJ_M, {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.10)}),
    "Mirror smile, cuts <=5%, raises <=15%": (ADJ_M, {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.15)}),
}
BASELINES = {
    "Bengen 4% (50/50 US)": vec.Params(rate=0.04, stocks=0.5),
    "Previous 8% plan": vec.Params(rate=0.08, stocks=0.8, intl=0.25, band=0.2, cut_step=0.3, raise_step=0.3,
                                   floor=0.5, ceiling=2.0, drift=-0.005),
    "Ratchet (30% intl)": vec.Params(rate=0.048, stocks=1.0, intl=0.30, band=0.0, cut_step=0.0, raise_step=0.13,
                                     drift=-0.009),
    "Blanchett smile, constant": vec.Params(rate=0.045, stocks=0.5, drift=-0.01, drift2=-0.02, drift3=-0.01),
}


class WeightedEvaluator(so.Evaluator):
    def __init__(self, df, gamma, max_extreme, weights, shape="decline"):
        super().__init__(df, gamma, max_extreme)
        self.weights = weights
        self.shape = shape

    def __call__(self, p):
        out = vec.simulate(p, *self.arrays(p.intl))
        return vec.metrics(p, out, self.gamma, weights=self.weights)

    def score(self, m):
        """Hard limits: extreme share, and the smile shape in the typical retiree's spending.
        decline: median spending never rises from one decade to the next.
        mirror:  years 11-20 <= years 1-10; years 21-30 above years 11-20 but not above years 1-10."""
        excess = max(0.0, m["extreme_share"] - self.max_extreme)
        t1, t2, t3 = (max(m[k], 1e-6) for k in ("typical_1_10", "typical_11_20", "typical_21_30"))
        if self.shape == "mirror":
            off = max(0.0, t2 / t1 - 1) + max(0.0, t3 / t1 - 1) + max(0.0, t2 / t3 - 1)
        else:
            off = max(0.0, t2 / t1 - 1) + max(0.0, t3 / t2 - 1)
        return m["ce"] - 100 * excess - 100 * off


def robustness(d, names, ev, rng, n_joint=400):
    """As smooth_optimize.robustness, but 'feasible' means both hard limits hold
    (extreme share and non-rising decades)."""
    ok = lambda m: ev.score(m) >= m["ce"] - 1e-9
    base = ev(so.make(d))
    rows = []
    for k in names:
        lo, hi = so.RANGES[k]
        for sgn in (-1, 1):
            if k in ("ceiling", "cash") and d[k] == 0.0:
                continue
            e = dict(d)
            if k in so.INTS:
                e[k] = int(np.clip(e[k] + sgn, lo, hi))
            else:
                e[k] = float(np.clip(e[k] + sgn * 0.1 * (hi - lo), lo, hi))
            m = ev(so.make(e))
            rows.append({"param": k, "direction": "+" if sgn > 0 else "−", "value": e[k],
                         "ce_change": m["ce"] - base["ce"], "extreme_share": m["extreme_share"], "feasible": ok(m)})
    joint = []
    for _ in range(n_joint):
        m = ev(so.make(so.nudge(d, names, rng, 0.05)))
        joint.append({"ce": m["ce"], "extreme_share": m["extreme_share"], "feasible": ok(m)})
    return pd.DataFrame(rows), pd.DataFrame(joint)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gamma", type=float, default=3.0)
    ap.add_argument("--who", default="couple", choices=["couple", "single", "male", "female", "none"])
    ap.add_argument("--max-extreme", type=float, default=0.10)
    ap.add_argument("--samples", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--families", default="", help="'|'-separated subset (default: all for the shape)")
    ap.add_argument("--name", default="")
    ap.add_argument("--max-intl", type=float, default=0.30)
    ap.add_argument("--intl-stress", action="store_true")
    ap.add_argument("--shape", choices=["decline", "mirror"], default="decline",
                    help="mirror: years 21-30 rise at the rate years 11-20 fell")
    a = ap.parse_args()
    families = MIRROR_FAMILIES if a.shape == "mirror" else SMILE_FAMILIES
    if a.shape == "mirror":
        base_make = so.make

        def mirror_make(params):
            p = base_make(params)
            d2 = p.drift if p.drift2 is None else p.drift2
            return replace(p, drift2=d2, drift3=-d2)
        so.make = mirror_make
    so.RANGES["intl"] = (0.0, a.max_intl)
    out = OUT / a.name if a.name else OUT
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    df = data.load(intl_series="intl_stress" if a.intl_stress else "intl")
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    n = len(vec.windows(df, 0.0)[0])
    max_extreme = np.floor(a.max_extreme * n + 1e-9) / n
    w = vec.survival_weights(who=a.who)
    ev = WeightedEvaluator(df, a.gamma, max_extreme, w, a.shape)
    wanted = a.families.split("|") if a.families else list(families)

    # make() in smooth_optimize builds Params from known fields, so drift2/drift3 pass straight through
    results, chosen, robust, found = [], {}, {}, []
    for label, p in BASELINES.items():
        m = ev(p)
        results.append({"family": label, "kind": "baseline", **{k: v for k, v in m.items() if k != "levels"}})
        chosen[label] = p
    base_ranges = dict(so.RANGES)
    for fam, (names, overrides) in families.items():
        if fam not in wanted:
            continue
        so.RANGES.clear()
        so.RANGES.update(base_ranges)
        so.RANGES.update(overrides)
        warm = [{k: (float(np.clip(v, *so.RANGES[k]))
                     if k in so.RANGES and k not in so.INTS and not (k in ("ceiling", "cash") and v == 0.0) else v)
                 for k, v in w.items()} for w in found]  # 0 = "no ceiling / no cash": keep it
        d, _ = so.optimise(names, ev, a.samples, rng, warm=warm)
        found.append(d)
        p = so.make(d)
        m = ev(p)
        results.append({"family": fam, "kind": "optimised", **{k: v for k, v in m.items() if k != "levels"}})
        chosen[fam] = p
        r1, rj = robustness(d, names, ev, rng)
        r1["family"], rj["family"] = fam, fam
        so.RANGES.clear()
        so.RANGES.update(base_ranges)
        robust[fam] = (r1, rj)
        print(f"{fam}: score ${m['ce']:.2f}, extreme {m['extreme_share']:.0%}, yrs 1-10 ${m['typical_1_10']:.2f}, "
              f"11-20 ${m['typical_11_20']:.2f}, 21-30 ${m['typical_21_30']:.2f}", file=sys.stderr)
    res = pd.DataFrame(results)
    res.to_csv(out / "smile_results.csv", index=False)
    if robust:
        pd.concat([r[0] for r in robust.values()]).to_csv(out / "robust_one_at_a_time.csv", index=False)
        pd.concat([r[1] for r in robust.values()]).to_csv(out / "robust_joint.csv", index=False)
    with open(out / "chosen_params.json", "w") as f:
        json.dump({k: v.as_dict() for k, v in chosen.items()}, f, indent=2)
    with open(out / "meta.json", "w") as f:
        json.dump({"gamma": a.gamma, "who": a.who, "shape": a.shape, "max_extreme": max_extreme, "samples": a.samples,
                   "seed": a.seed, "survival_weights": [round(x, 4) for x in w]}, f, indent=2)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
