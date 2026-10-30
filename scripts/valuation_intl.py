"""Do the valuation rules change with 30% of stocks held internationally?

Runs each rule twice, with US stocks only and with 70% US / 30% developed ex-US stocks (BENGEN_INTL=0.3, see
valuation.load), re-optimising every rule for each case. Reports SAFEMAX in sample and walk-forward (starts
1950-1993), the typical retiree's highest rate, and real wealth by January 2023 for retirements started 1995-2010.

    python scripts/valuation_intl.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "valuation"


def one_case():
    sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
    from bengen import valuation as V
    import valuation_duration as vd
    import valuation_duration50 as v5
    import valuation_rolling as VR
    share = float(os.environ.get("BENGEN_INTL", "0"))
    rows = []
    for safe in ("bills", "bonds"):
        d = vd.Data(safe)
        vr = VR.Data(safe)
        three_p = VR.fit(VR.three, vr.S, vr.B, vr.rel_med, vr.rel10)
        sb0 = vd.best(d.S, d.B, d.rel, d.state)
        sb50 = vd.best(d.S, d.B, d.rel, d.state, triples=v5.TRIPLES)
        rules = {
            "Fixed 60%": ("fixed", 0.6), "Fixed 75%": ("fixed", 0.75), "Pfau-Kitces 60/45/30": ("kp", None),
            "3 levels vs median": ("three", three_p), "Slow bend 0-100%": ("bend", sb0), "Slow bend 50-100%": ("bend", sb50),
            "50% normally, 100% when cheap": ("bend", {"s_min": .5, "s_normal": .5, "s_max": 1.0, "hi": 1.15,
                                                      "decay": "reset", "ramp": 10, "cheap_years": 0}),
        }

        def share_matrix(kind, p, idx):
            if kind == "fixed":
                return np.full(d.S[idx].shape, p)
            if kind == "kp":
                return VR.kp(None, vr.rel_med[idx], None)
            if kind == "three":
                return VR.three(p, vr.rel_med[idx], None)
            return vd.shares_for(p, d.rel[idx], {k: (r[idx], c[idx]) for k, (r, c) in d.state.items()})

        def share_years(kind, p, yrs):
            if kind == "fixed":
                return np.full(len(yrs), p)
            rel = vd.REL_ALL.loc[yrs].values
            if kind == "kp":
                return np.where(rel < 2 / 3, .6, np.where(rel > 4 / 3, .3, .45))
            if kind == "three":
                return np.where(rel < 2 / 3, p["u"], np.where(rel > 4 / 3, p["o"], p["f"]))
            return v5.series_share(p).loc[yrs].values

        allk = np.ones(len(vd.STARTS), bool)
        for name, (kind, p) in rules.items():
            w = share_matrix(kind, p, allk)
            sm = V.safemax(w * d.S + (1 - w) * d.B)
            # walk-forward for optimised rules
            if kind in ("three", "bend") and name != "50% normally, 100% when cheap":
                rates, cache = [], {}
                for y in range(1950, vd.LAST + 1):
                    k = vd.STARTS <= y - 30
                    if k.sum() not in cache:
                        if kind == "three":
                            cache[k.sum()] = VR.fit(VR.three, vr.S[k], vr.B[k], vr.rel_med[k], vr.rel10[k])
                        else:
                            tri = v5.TRIPLES if "50-100" in name else vd.TRIPLES[np.all(np.isclose(np.round(vd.TRIPLES * 10) / 10, vd.TRIPLES), axis=1)]
                            cache[k.sum()] = vd.best(d.S[k], d.B[k], d.rel[k], {kk: (r[k], c[k]) for kk, (r, c) in d.state.items()}, triples=tri)
                    i = d.idx([y])
                    ww = share_matrix(kind, cache[k.sum()], i)
                    rates.append(V.safemax(ww * d.S[i] + (1 - ww) * d.B[i])[0])
                wf = np.array(rates)
            else:
                wf = sm[vd.STARTS >= 1950]
            rw = v5.recent_wealth(lambda yrs, kind=kind, p=p: share_years(kind, p, yrs), safe)
            rows.append({"intl share": share, "safe": safe, "rule": name, "SAFEMAX %": sm.min() * 100,
                         "walk-forward SAFEMAX %": wf.min() * 100, "walk-forward median MWR %": np.median(wf) * 100,
                         "median MWR %": np.median(sm) * 100, "recent wealth avg": np.mean(list(rw.values())),
                         "settings": json.dumps({k: (round(float(v), 3) if not isinstance(v, str) else v) for k, v in (p or {}).items()}) if isinstance(p, dict) else str(p)})
    pd.DataFrame(rows).to_csv(OUT / f"intl_case_{share:.1f}.csv", index=False)


def main():
    for share in ("0", "0.3"):
        env = dict(os.environ, BENGEN_INTL=share)
        subprocess.run([sys.executable, __file__, "--case"], env=env, check=True)
    df = pd.concat([pd.read_csv(OUT / f"intl_case_{s:.1f}.csv") for s in (0.0, 0.3)])
    df.to_csv(OUT / "intl_comparison.csv", index=False)
    with pd.option_context("display.width", 250, "display.precision", 2):
        for m in ("walk-forward SAFEMAX %", "walk-forward median MWR %", "SAFEMAX %", "recent wealth avg"):
            print(f"\n{m}")
            t = df.pivot_table(index=["safe", "rule"], columns="intl share", values=m)
            t["change"] = t[0.3] - t[0.0]
            print(t.round(2).to_string())
        print(df[df["intl share"] == 0.3][["safe", "rule", "settings"]].to_string(index=False))


if __name__ == "__main__":
    one_case() if "--case" in sys.argv else main()
