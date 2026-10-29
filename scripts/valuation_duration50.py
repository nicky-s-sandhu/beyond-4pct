"""Slow-bend valuation rule with the stock share held between 50% and 100%.

Same rule as valuation_duration.py (stock share bends from s_normal towards s_min the longer CAPE stays elevated
against its median to date, s_max when cheap), with s_min = 50% and s_max = 100% fixed as requested. Optimised:
s_normal (50-100%), the elevated threshold, recovery and cheap response; ramp 10 years (5, 15, 20 as a check).
Judged on SAFEMAX in sample, split by time and walk-forward, and also on retirements that started 1995-2010
(not yet 30 years old): their real wealth by January 2023 at a fixed 4% withdrawal.

    python scripts/valuation_duration50.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from bengen import valuation as V  # noqa: E402
import valuation_duration as vd  # noqa: E402

OUT = ROOT / "output" / "valuation"
D, LAST, STARTS = vd.D, vd.LAST, vd.STARTS
G = np.round(np.arange(0.5, 1.0001, 0.05), 2)
TRIPLES = np.array([(0.5, m, 1.0) for m in G])                 # s_min 50%, s_normal 50-100%, s_max 100%
RECENT = (1995, 2000, 2005, 2010)


def series_share(p):
    run, _ = vd.states(p["hi"], p["decay"])
    return vd.duration_shares(run, vd.REL_ALL, p)


def recent_wealth(share_by_year, safe):
    out = {}
    for start in RECENT:
        yrs = list(range(start, 2023))
        S, B = D["real_stocks"].loc[yrs].values, D[f"real_{safe}"].loc[yrs].values
        w = share_by_year(yrs)
        W = 100.0
        for t in range(len(yrs)):
            W = max(W - 4, 0) * (1 + w[t] * S[t] + (1 - w[t]) * B[t])
        out[f"wealth 2023, retired {start}"] = W
    return out


def main():
    rows, params = [], {}
    for safe in ("bills", "bonds"):
        d = vd.Data(safe)
        p10 = vd.best(d.S, d.B, d.rel, d.state, triples=TRIPLES)
        pany = vd.best(d.S, d.B, d.rel, d.state, ramps=(5, 10, 15, 20), triples=TRIPLES)
        p0 = json.loads((OUT / "duration_params.json").read_text())[safe]["ramp 10"]
        params[safe] = {"50-100, ramp 10": p10, "50-100, ramp optimised": pany}
        rules = {"Fixed 60%": lambda yrs, p=None: np.full(len(yrs), 0.6),
                 "Fixed 75%": lambda yrs, p=None: np.full(len(yrs), 0.75),
                 "Slow bend 0-100% (previous)": lambda yrs, p=p0: series_share(p).loc[yrs].values,
                 "Slow bend 50-100%, 10-yr ramp (new)": lambda yrs, p=p10: series_share(p).loc[yrs].values,
                 "Slow bend 50-100%, ramp optimised": lambda yrs, p=pany: series_share(p).loc[yrs].values}
        settings = {"Fixed 60%": "60% stocks", "Fixed 75%": "75% stocks", "Slow bend 0-100% (previous)": vd.describe(p0),
                    "Slow bend 50-100%, 10-yr ramp (new)": vd.describe(p10),
                    "Slow bend 50-100%, ramp optimised": vd.describe(pany)}
        fixed = {"Fixed 60%": 0.6, "Fixed 75%": 0.75}
        for name, fn in rules.items():
            w = np.array([fn(list(range(y, y + 30))) for y in STARTS])
            st = vd.stats(name, w, d.S, d.B, STARTS, settings[name])
            # walk-forward (fixed rules need none)
            if name in fixed:
                wf = V.safemax(fixed[name] * d.S + (1 - fixed[name]) * d.B)[STARTS >= 1950]
            elif name.startswith("Slow bend 0-100"):
                wf = None
            else:
                rates, cache = [], {}
                ramps = (10,) if "10-yr" in name else (5, 10, 15, 20)
                for y in range(1950, LAST + 1):
                    k = STARTS <= y - 30
                    if k.sum() not in cache:
                        cache[k.sum()] = vd.best(d.S[k], d.B[k], d.rel[k],
                                                 {key: (r[k], c[k]) for key, (r, c) in d.state.items()},
                                                 ramps=ramps, triples=TRIPLES)
                    q = cache[k.sum()]
                    i = d.idx([y])
                    ww = vd.shares_for(q, d.rel[i], {key: (r[i], c[i]) for key, (r, c) in d.state.items()})
                    rates.append(V.safemax(ww * d.S[i] + (1 - ww) * d.B[i])[0])
                wf = np.array(rates)
            if name.startswith("Slow bend 0-100"):
                o = pd.read_csv(OUT / "duration_out_of_sample.csv")
                r = o[(o.safe == safe) & (o.rule == "Slow bend, 10-year ramp (new)") & o.test.str.startswith("walk")].iloc[0]
                wf_min, wf_med = r["test SAFEMAX %"], r["test median MWR %"]
            else:
                wf_min, wf_med = wf.min() * 100, np.median(wf) * 100
            rows.append({"safe": safe, **st, "walk-forward SAFEMAX %": wf_min, "walk-forward median MWR %": wf_med,
                         "stocks Jan 2026 %": float(fn([2026])[0]) * 100 if name not in fixed else fixed[name] * 100,
                         **recent_wealth(fn, safe)})
        print(safe, "done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "duration50.csv", index=False)
    (OUT / "duration50_params.json").write_text(json.dumps(params, indent=1, default=float))
    cols = ["safe", "rule", "SAFEMAX %", "walk-forward SAFEMAX %", "median MWR %", "walk-forward median MWR %",
            "avg stocks %", "avg stocks since 1995 %", "stocks Jan 2026 %"] + [f"wealth 2023, retired {y}" for y in RECENT]
    with pd.option_context("display.width", 280, "display.max_colwidth", 150, "display.precision", 2):
        print(df[cols].to_string(index=False))
        print(df[["safe", "rule", "settings"]].to_string(index=False))


if __name__ == "__main__":
    main()
