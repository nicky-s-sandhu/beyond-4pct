"""Declining spending with a fixed floor and capped raises.

Plan: real spending planned to decline at one steady rate (optimiser picks 0% to -3%/yr).
Floor: never below 75% of first-year spending, fixed in real terms (--floor).
Adjustments: cut by cut_step when the withdrawal rate is above rate x (1 + band),
raise by raise_step when below rate x (1 - band); raises capped per family.
Score: certainty-equivalent spending (risk aversion 3), each year weighted by the
chance a 65-year-old couple is alive. Hard limits: at most 10% of retirees cut 50%+
below plan or run out, and typical spending never rises from one decade to the next.
International <= 30% of stocks. No cash bucket.

    python scripts/decline_optimize.py
    python scripts/decline_optimize.py --who single --families "Cuts <=5%, raises <=10%" --name single
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
import smile_optimize as sm  # noqa: E402  (WeightedEvaluator with the decline rule)

OUT = ROOT / "output" / "decline"
NAMES = ["rate", "stocks", "intl", "band", "cut_step", "raise_step", "ceiling", "drift"]
FAMILIES = {
    "Cuts <=5%, raises <=5%": {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.05)},
    "Cuts <=5%, raises <=10%": {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.10)},
    "Cuts <=5%, raises <=15%": {"cut_step": (0.002, 0.05), "raise_step": (0.0, 0.15)},
    "Any cuts, raises <=10%": {"cut_step": (0.002, 0.35), "raise_step": (0.0, 0.10)},
}
BASELINES = {
    "Bengen 4% (50/50 US)": vec.Params(rate=0.04, stocks=0.5),
    "Previous 8% plan": vec.Params(rate=0.08, stocks=0.8, intl=0.25, band=0.2, cut_step=0.3, raise_step=0.3,
                                   floor=0.5, ceiling=2.0, drift=-0.005),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--floor", type=float, default=0.75, help="floor as a share of first-year spending")
    ap.add_argument("--gamma", type=float, default=3.0)
    ap.add_argument("--who", default="couple", choices=["couple", "single", "male", "female", "none"])
    ap.add_argument("--max-extreme", type=float, default=0.10)
    ap.add_argument("--max-intl", type=float, default=0.30)
    ap.add_argument("--intl-stress", action="store_true")
    ap.add_argument("--samples", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--families", default="", help="'|'-separated subset")
    ap.add_argument("--name", default="")
    a = ap.parse_args()
    out = OUT / a.name if a.name else OUT
    out.mkdir(parents=True, exist_ok=True)

    so.RANGES.update({"intl": (0.0, a.max_intl), "drift": (-0.03, 0.0)})
    base_make = so.make

    def make_fixed_floor(params):
        p = base_make(params)
        return replace(p, floor=a.floor, floor_flat=True, drift2=None, drift3=None, cash=0.0, bucket=False)
    so.make = make_fixed_floor

    rng = np.random.default_rng(a.seed)
    df = data.load(intl_series="intl_stress" if a.intl_stress else "intl")
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    n = len(vec.windows(df, 0.0)[0])
    max_extreme = np.floor(a.max_extreme * n + 1e-9) / n
    w = vec.survival_weights(who=a.who)
    ev = sm.WeightedEvaluator(df, a.gamma, max_extreme, w, "decline")
    wanted = a.families.split("|") if a.families else list(FAMILIES)

    results, chosen, found = [], {}, []
    for label, p in BASELINES.items():
        m = ev(p)
        results.append({"family": label, "kind": "baseline", **{k: v for k, v in m.items() if k != "levels"}})
        chosen[label] = p
    base_ranges = dict(so.RANGES)
    robust = []
    for fam, overrides in FAMILIES.items():
        if fam not in wanted:
            continue
        so.RANGES.clear(); so.RANGES.update(base_ranges); so.RANGES.update(overrides)
        warm = [{k: (float(np.clip(v, *so.RANGES[k])) if k in so.RANGES and not (k == "ceiling" and v == 0.0)
                     else v) for k, v in d.items()} for d in found]
        d, _ = so.optimise(NAMES, ev, a.samples, rng, warm=warm)
        found.append(d)
        p = so.make(d)
        m = ev(p)
        results.append({"family": fam, "kind": "optimised", **{k: v for k, v in m.items() if k != "levels"}})
        chosen[fam] = p
        r1, rj = sm.robustness(d, NAMES, ev, rng)
        r1["family"], rj["family"] = fam, fam
        robust.append((r1, rj))
        print(f"{fam}: score ${m['ce']:.2f}, extreme {m['extreme_share']:.0%}, start {p.rate:.1%}, "
              f"yrs ${m['typical_1_10']:.2f}/${m['typical_11_20']:.2f}/${m['typical_21_30']:.2f}", file=sys.stderr)
    so.RANGES.clear(); so.RANGES.update(base_ranges)
    pd.DataFrame(results).to_csv(out / "decline_results.csv", index=False)
    if robust:
        pd.concat([r[0] for r in robust]).to_csv(out / "robust_one_at_a_time.csv", index=False)
        pd.concat([r[1] for r in robust]).to_csv(out / "robust_joint.csv", index=False)
    with open(out / "chosen_params.json", "w") as f:
        json.dump({k: v.as_dict() for k, v in chosen.items()}, f, indent=2)
    with open(out / "meta.json", "w") as f:
        json.dump({"floor": a.floor, "gamma": a.gamma, "who": a.who, "max_extreme": max_extreme,
                   "max_intl": a.max_intl, "intl_stress": a.intl_stress, "samples": a.samples, "seed": a.seed,
                   "survival_weights": [round(x, 4) for x in w]}, f, indent=2)


if __name__ == "__main__":
    main()
