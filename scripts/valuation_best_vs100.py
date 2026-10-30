"""All-stocks baseline (100% stocks, 30% of it international) against the ECY rules, on every test set."""
import sys
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation_best as vb
from bengen import stockrule as sr

RULES = {"Fixed 100%": sr.Rule("none", 1.0), "Fixed 80% (plan)": sr.Rule("none", 0.8),
         "ECY 80%, +1/-1, 50-100%": sr.Rule("ecy", 0.8, 1, 1.0, 0.5),
         "ECY 80%, +1/-1.5, 0-100%": sr.Rule("ecy", 0.8, 1, 1.5, 0.0)}
if __name__ == "__main__":
    dp, dl = vb.frame("plan"), vb.frame("long")
    sets = {"1928-2025": vb.Set.boot(dp), "1881-2022": vb.Set.boot(dl),
            "1928-1976 only": vb.Set.boot(dp, (1928, 1976)), "1977-2025 only": vb.Set.boot(dp, (1977, 2025))}
    hist = vb.Set.hist(dp)
    rows = []
    for name, rule in RULES.items():
        for sn, st in sets.items():
            s = vb.score(rule, st)
            fixed = vb.score(rule, st, rate=0.065)   # at the plan's 6.5% start
            W = sr.shares(rule, st.X[rule.signal])
            ro = sr.simulate(replace(vb.P, rate=0.065), W, st.S, st.B, st.I)["depleted"].mean() * 100
            rows.append({"rule": name, "set": sn, "rate_2pct": s["rate"], "ce_2pct": s["ce"], "typ_1_10": s["typ_1_10"],
                         "p10_year": s["p10_year"], "cut30": s["cut30"], "median_final": s["median_final"],
                         "runout_at_6.5": ro, "ce_at_6.5": fixed["ce"], "median_final_at_6.5": fixed["median_final"]})
        h = vb.score(rule, hist, rate=0.065)
        rows.append({"rule": name, "set": "historical 1928-1996 @6.5%", "ce_at_6.5": h["ce"], "runout_at_6.5": h["ran_out"],
                     "typ_1_10": h["typ_1_10"], "p10_year": h["p10_year"], "cut30": h["cut30"],
                     "median_final_at_6.5": h["median_final"]})
    d = pd.DataFrame(rows)
    d.to_csv(vb.OUT / "best_vs100.csv", index=False)
    pd.set_option("display.width", 250)
    print(d.round(2).to_string())
