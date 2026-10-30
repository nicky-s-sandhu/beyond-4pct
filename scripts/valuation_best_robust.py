"""Simple candidate stock rules scored on every test set (rate at 2% run-out, smooth-spending score)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation_best as vb
from bengen import stockrule as sr

CANDS = {
    "Fixed 80% (plan)": sr.Rule("none", 0.8),
    "CAPE best (70%, +1/-0.5, 50-100%)": sr.Rule("cape", 0.7, 1, 0.5, 0.5),
    "ECY best (85%, +0.375/-1.5, 0-100%)": sr.Rule("ecy", 0.85, 0.375, 1.5, 0.0),
    "ECY 80%, +1/-1.5, 0-100%": sr.Rule("ecy", 0.8, 1, 1.5, 0.0),
    "ECY 80%, +1/-1.5, 30-100%": sr.Rule("ecy", 0.8, 1, 1.5, 0.3),
    "ECY 80%, +1/-1.5, 50-100%": sr.Rule("ecy", 0.8, 1, 1.5, 0.5),
    "ECY 80%, +1/-1, 50-100%": sr.Rule("ecy", 0.8, 1, 1.0, 0.5),
    "ECY 80%, +0/-1.5, 0-80% (only cuts)": sr.Rule("ecy", 0.8, 0, 1.5, 0.0),
    "ECY 80%, +1/-0 (only buys)": sr.Rule("ecy", 0.8, 1, 0, 0.0),
}
if __name__ == "__main__":
    dp, dl = vb.frame("plan"), vb.frame("long")
    sets = {"1928-2025": vb.Set.boot(dp), "1881-2022": vb.Set.boot(dl),
            "1928-1976 only": vb.Set.boot(dp, (1928, 1976)), "1977-2025 only": vb.Set.boot(dp, (1977, 2025))}
    rows = []
    for name, rule in CANDS.items():
        row = {"rule": name}
        for sn, st in sets.items():
            s = vb.score(rule, st)
            row[f"{sn} rate"], row[f"{sn} ce"] = s["rate"], s["ce"]
            if sn == "1928-2025":
                row.update({"typ_1_10": s["typ_1_10"], "cut30": s["cut30"], "median_final": s["median_final"],
                            "avg_stocks": s["avg_stocks"]})
        rows.append(row)
        print(row, flush=True)
    pd.DataFrame(rows).to_csv(vb.OUT / "best_robust.csv", index=False)
