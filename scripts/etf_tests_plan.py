"""The four tests with the recommended plan's spending settings unchanged (only the starting rate re-solved for 2%
run-out), on reshuffled 1928-2020, and on each half of that history. Output output/etf_tests/plan_settings.csv"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_tests as et

if __name__ == "__main__":
    df = et.frame()
    sets = {"1928-2020": et.boot(df), "1928-74 only": et.boot(df, (1928, 1974)), "1975-2020 only": et.boot(df, (1975, 2020))}
    rows = []
    for port in et.PORTS:
        row = {"portfolio": port[0]}
        for sn, st in sets.items():
            R, Ws = et.returns(port, st)
            e = et.evaluate(et.P0, R, st)
            e65 = et.evaluate(et.P0, R, st, rate=0.065)
            row.update({f"{sn} rate": e["rate"], f"{sn} ce": e["ce"]})
            if sn == "1928-2020":
                row.update({"typ_1_10": e["typ_1_10"], "p10_year": e["p10_year"], "cut30": e["cut30"],
                            "median_final": e["median_final"], "ran_out_at_6.5": e65["ran_out"], "avg_stocks": Ws.mean() * 100})
        rows.append(row)
    d = pd.DataFrame(rows)
    d.to_csv(et.OUT / "plan_settings.csv", index=False)
    pd.set_option("display.width", 250)
    print(d.round(2).to_string())
