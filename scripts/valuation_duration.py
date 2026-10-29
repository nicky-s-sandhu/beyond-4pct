"""Valuation rule with memory: lower the stock share slowly the longer CAPE stays elevated.

CAPE is judged against its median to date (the informative signal from the Pfau-Kitces reproduction). A January is
"elevated" when CAPE > hi x median. The stock share is s_normal after 0 elevated years and bends linearly to s_min
after `ramp` consecutive elevated years (10 by default, as requested); once CAPE is no longer elevated the count
resets to 0 (or, in the "gradual" variant, falls by one a year). When CAPE is cheap (< 2/3 of the median) the share
moves to s_max at once, or over 3 cheap years. The count is a market state, so a retiree inherits however long CAPE
had already been elevated when they retired.

Optimised: s_min, s_normal, s_max (0-100% in 5-point steps), hi, recovery and cheap response; the ramp length is
10 years in the main run with 5, 15 and 20 as a sensitivity check. Objective and checks as before: SAFEMAX
(start-of-year fixed real withdrawals, Shiller data, starts 1890-1993), split by time both ways, walk-forward.

    python scripts/valuation_duration.py
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import valuation as V  # noqa: E402
import valuation_rolling as VR  # noqa: E402

OUT = ROOT / "output" / "valuation"
D = V.load()
LAST = int(D.index.max()) - 29
STARTS = np.arange(1890, LAST + 1)
HIS = (1.15, 1.25, 4 / 3, 1.5)
DECAYS = ("reset", "gradual")
CHEAPS = (0, 3)
G = np.round(np.arange(0, 1.0001, 0.05), 2)
TRIPLES = np.array([(a, b, c) for a, b, c in itertools.product(G, G, G) if a <= b <= c])   # s_min <= s_normal <= s_max


def cape_history():
    """CAPE relative to its median to date for every January through 2026 (adds the repo's 2023-26 CAPEs)."""
    c = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"].loc[1881:]
    return c / c.expanding().median()


REL_ALL = cape_history()


def states(hi, decay):
    run = V.elevated_run(REL_ALL, hi, decay)
    cheap = V.elevated_run(1 / REL_ALL, 1.5, "reset")          # consecutive years with rel < 2/3
    return run, cheap


def take(series, starts):
    return np.array([series.loc[y:y + 29].values for y in starts])


class Data:
    def __init__(self, safe):
        self.S, self.B = take(D["real_stocks"], STARTS), take(D[f"real_{safe}"], STARTS)
        self.rel = take(REL_ALL, STARTS)
        self.state = {(hi, dc): tuple(take(x, STARTS) for x in states(hi, dc)) for hi in HIS for dc in DECAYS}

    def idx(self, starts):
        return np.isin(STARTS, starts)


def weights(rel, run, cheap_run, ramp, cheap_years):
    """Decompose the stock share as a*s_normal + b*s_min + c*s_max."""
    frac = np.clip(run / ramp, 0, 1)
    cheap = rel < 2 / 3
    if cheap_years == 0:
        g = np.ones_like(rel)
    else:
        g = np.clip(cheap_run / cheap_years, 0, 1)
    a = np.where(cheap, 1 - g, 1 - frac)
    b = np.where(cheap, 0.0, frac)
    c = np.where(cheap, g, 0.0)
    return a, b, c


def best(S, B, rel, state, ramps=(10,), triples=TRIPLES, chunk=600):
    top = (-1.0, -1.0, None)
    X = S - B
    for (hi, dc), (run, cheap_run) in state.items():
        for ramp, cy in itertools.product(ramps, CHEAPS):
            a, b, c = weights(rel, run, cheap_run, ramp, cy)
            for i in range(0, len(triples), chunk):
                t = triples[i:i + chunk]                                    # columns: s_min, s_normal, s_max
                w = (t[:, 1, None, None] * a + t[:, 0, None, None] * b + t[:, 2, None, None] * c)
                R = B + w * X
                disc = np.cumprod(np.concatenate([np.ones(R.shape[:2] + (1,)), 1 / (1 + R[..., :-1])], axis=2), axis=2)
                sm = 1 / disc.sum(axis=2)                                  # (k, n)
                mins, meds = sm.min(axis=1), np.median(sm, axis=1)
                j = np.lexsort((meds, np.round(mins, 6)))[-1]
                key = (round(mins[j], 6), meds[j])
                if key > top[:2]:
                    top = key + ({"s_min": t[j, 0], "s_normal": t[j, 1], "s_max": t[j, 2], "hi": hi, "decay": dc,
                                  "ramp": ramp, "cheap_years": cy},)
    return top[2]


def shares_for(p, rel, state):
    run, cheap_run = state[(p["hi"], p["decay"])]
    a, b, c = weights(rel, run, cheap_run, p["ramp"], p["cheap_years"])
    return a * p["s_normal"] + b * p["s_min"] + c * p["s_max"]


def describe(p):
    return (f"{p['s_normal']:.0%} normally, bending to {p['s_min']:.0%} after {p['ramp']} elevated years "
            f"(elevated = CAPE > {p['hi']:.2f}x median; {p['decay']} recovery); {p['s_max']:.0%} when cheap"
            + (" at once" if p["cheap_years"] == 0 else f" over {p['cheap_years']} yrs"))


def stats(name, w, S, B, starts, settings):
    R = w * S + (1 - w) * B
    sm, tw = V.safemax(R), V.terminal_wealth(R)
    yrs = starts[:, None] + np.arange(30)
    late = starts >= 1980
    return {"rule": name, "settings": settings, "SAFEMAX %": sm.min() * 100, "worst start": int(starts[np.argmin(sm)]),
            "median MWR %": np.median(sm) * 100, "median wealth at 4%": np.median(tw), "avg stocks %": w.mean() * 100,
            "avg stocks since 1995 %": w[yrs >= 1995].mean() * 100,
            "median MWR 1980-93 starts %": np.median(sm[late]) * 100}


def main():
    rows, oos, params = [], [], {}
    for safe in ("bills", "bonds"):
        d = Data(safe)
        vr = VR.Data(safe)
        # baselines (same starts) from the previous experiment's code
        base = {"Fixed 60%": (None, {}), "Pfau-Kitces 60/45/30": (VR.kp, {}),
                "3 levels vs median to date": (VR.three, VR.fit(VR.three, vr.S, vr.B, vr.rel_med, vr.rel10)),
                "Sliding vs 10-year average": (VR.ramp, VR.fit(VR.ramp, vr.S, vr.B, vr.rel_med, vr.rel10))}
        for name, (rule, p) in base.items():
            rows.append({"safe": safe, **stats(name, VR.shares(rule, p, vr.rel_med, vr.rel10), vr.S, vr.B, STARTS,
                                               VR.describe(rule, p) if rule else "60% stocks")})
        p10 = best(d.S, d.B, d.rel, d.state)
        pany = best(d.S, d.B, d.rel, d.state, ramps=(5, 10, 15, 20))
        params[safe] = {"ramp 10": p10, "ramp optimised": pany}
        for name, p in (("Slow bend, 10-year ramp (new)", p10), ("Slow bend, ramp optimised", pany)):
            rows.append({"safe": safe, **stats(name, shares_for(p, d.rel, d.state), d.S, d.B, STARTS, describe(p))})
        # out of sample: splits and walk-forward, 10-year ramp, coarser grid for speed
        coarse = TRIPLES[np.all(np.isclose(np.round(TRIPLES * 10) / 10, TRIPLES), axis=1)]
        for label, (tr, te) in {"fit 1890-1941, test 1942-1993": (range(1890, 1942), range(1942, LAST + 1)),
                                "fit 1942-1993, test 1890-1941": (range(1942, LAST + 1), range(1890, 1942))}.items():
            ktr, kte = d.idx(list(tr)), d.idx(list(te))
            sub = lambda k: {key: (r[k], c[k]) for key, (r, c) in d.state.items()}
            p = best(d.S[ktr], d.B[ktr], d.rel[ktr], sub(ktr), triples=coarse)
            w = shares_for(p, d.rel[kte], sub(kte))
            sm = V.safemax(w * d.S[kte] + (1 - w) * d.B[kte])
            oos.append({"safe": safe, "test": label, "rule": "Slow bend, 10-year ramp (new)", "test SAFEMAX %": sm.min() * 100,
                        "test median MWR %": np.median(sm) * 100, "settings": describe(p)})
        rates, cache = [], {}
        for y in range(1950, LAST + 1):
            k = STARTS <= y - 30
            if k.sum() not in cache:
                cache[k.sum()] = best(d.S[k], d.B[k], d.rel[k], {key: (r[k], c[k]) for key, (r, c) in d.state.items()},
                                      triples=coarse)
            p = cache[k.sum()]
            i = d.idx([y])
            w = shares_for(p, d.rel[i], {key: (r[i], c[i]) for key, (r, c) in d.state.items()})
            rates.append(V.safemax(w * d.S[i] + (1 - w) * d.B[i])[0])
        oos.append({"safe": safe, "test": "walk-forward, starts 1950-1993", "rule": "Slow bend, 10-year ramp (new)",
                    "test SAFEMAX %": np.min(rates) * 100, "test median MWR %": np.median(rates) * 100,
                    "settings": "re-fit each year; last: " + describe(p)})
        print(safe, "done", flush=True)
    prev = pd.read_csv(OUT / "rolling_out_of_sample.csv")
    prev = prev[prev.rule.isin(["Fixed 60%", "Pfau-Kitces 60/45/30", "Optimised 3 levels vs median to date",
                                "Sliding vs 10-year average (new)"])]
    o = pd.concat([prev, pd.DataFrame(oos)], ignore_index=True)
    a = pd.DataFrame(rows)
    a.to_csv(OUT / "duration_in_sample.csv", index=False); o.to_csv(OUT / "duration_out_of_sample.csv", index=False)
    (OUT / "duration_params.json").write_text(json.dumps(params, indent=1, default=float))
    with pd.option_context("display.width", 260, "display.max_colwidth", 140, "display.precision", 2):
        print(f"\nIn sample, starts 1890-{LAST}")
        print(a.drop(columns="settings").to_string(index=False))
        print(a[["safe", "rule", "settings"]].to_string(index=False))
        print("\nOut of sample SAFEMAX %")
        print(o.pivot_table(index=["safe", "rule"], columns="test", values="test SAFEMAX %").round(2).to_string())
        print("\nOut of sample median MWR %")
        print(o.pivot_table(index=["safe", "rule"], columns="test", values="test median MWR %").round(2).to_string())
    for safe in ("bills", "bonds"):
        p = params[safe]["ramp 10"]
        run, cheap_run = states(p["hi"], p["decay"])
        w = duration_shares(run, REL_ALL, p)
        print(f"{safe}: stock share Jan 2020-2026 under the 10-year-ramp rule:", (w.loc[2020:2026] * 100).round(0).astype(int).to_dict())


def duration_shares(run, rel, p):
    a, b, c = weights(rel.values, run.values, V.elevated_run(1 / rel, 1.5, "reset").values, p["ramp"], p["cheap_years"])
    return pd.Series(a * p["s_normal"] + b * p["s_min"] + c * p["s_max"], index=rel.index)


if __name__ == "__main__":
    main()
