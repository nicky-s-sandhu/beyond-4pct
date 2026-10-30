"""The ECY stock rule with Shiller's published ECY series ("ecys") instead of our own calculation ("ecy").

1. The same rules (no re-tuning) on every test set.
2. A fresh search with Shiller's series: full sample, split-sample both ways, placebo shifts.
Outputs output/valuation/shiller_ecy_*.csv
"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation_best as vb
from bengen import stockrule as sr

PAIRS = {"80%, +1/-1, 50-100%": (0.8, 1, 1.0, 0.5), "80%, +1/-1.5, 0-100%": (0.8, 1, 1.5, 0.0)}


def main():
    dp, dl = vb.frame("plan"), vb.frame("long")
    sets = {"1928-2025": vb.Set.boot(dp), "1881-2022": vb.Set.boot(dl),
            "1928-1976 only": vb.Set.boot(dp, (1928, 1976)), "1977-2025 only": vb.Set.boot(dp, (1977, 2025))}
    rows = []
    rules = {"Fixed 80% (plan)": sr.Rule("none", 0.8), "Fixed 100%": sr.Rule("none", 1.0)}
    for name, (c, kc, kd, lo) in PAIRS.items():
        rules[f"Our ECY {name}"] = sr.Rule("ecy", c, kc, kd, lo)
        rules[f"Shiller ECY {name}"] = sr.Rule("ecys", c, kc, kd, lo)
    for name, rule in rules.items():
        for sn, st in sets.items():
            s = vb.score(rule, st)
            rows.append({"rule": name, "set": sn, **s})
        print(name, [round(r["rate"], 2) for r in rows[-4:]], flush=True)
    pd.DataFrame(rows).to_csv(vb.OUT / "shiller_ecy_same_rules.csv", index=False)

    # fresh search with Shiller's series
    log = []
    full = sets["1928-2025"]
    res = vb.search(full, vb.grid(signals=("ecys",)))
    res = pd.concat([res, vb.refine(full, res)]).drop_duplicates("label").sort_values("ce", ascending=False)
    res.to_csv(vb.OUT / "shiller_ecy_search.csv", index=False)
    top = res[res.signal == "ecys"].iloc[0]
    top50 = res[(res.signal == "ecys") & (res.lo >= 0.5)].iloc[0]
    log += [f"best: {top.label} rate {top.rate:.2f} ce {top.ce:.2f}",
            f"best >=50%: {top50.label} rate {top50.rate:.2f} ce {top50.ce:.2f}"]
    halves = {"early": (1928, 1976), "late": (1977, 2025)}
    split = []
    for fit, test in (("early", "late"), ("late", "early")):
        f, t = sets[f"{halves[fit][0]}-{halves[fit][1]} only"], sets[f"{halves[test][0]}-{halves[test][1]} only"]
        r = vb.search(f, vb.grid(signals=("ecys",)))
        r = pd.concat([r, vb.refine(f, r)]).sort_values("ce", ascending=False)
        for kind, sub in (("fixed", r[r.signal == "none"]), ("Shiller ECY", r[r.signal == "ecys"]),
                          ("Shiller ECY >=50%", r[(r.signal == "ecys") & (r.lo >= 0.5)])):
            rule = vb.to_rule(sub.iloc[0])
            i, o = vb.score(rule, f), vb.score(rule, t)
            split.append({"fit": fit, "test": test, "kind": kind, "rule": rule.label(), "rate_in": i["rate"],
                          "ce_in": i["ce"], "rate_out": o["rate"], "ce_out": o["ce"]})
            log.append(f"split {fit}->{test} {kind}: {rule.label()} in {i['rate']:.2f}/{i['ce']:.2f} "
                       f"out {o['rate']:.2f}/{o['ce']:.2f}")
    pd.DataFrame(split).to_csv(vb.OUT / "shiller_ecy_split.csv", index=False)
    small = vb.grid(signals=("ecys",))
    real = vb.search(full, small)
    gain = real[real.signal == "ecys"].iloc[0].ce - real[real.signal == "none"].iloc[0].ce
    plc = []
    for shift in (20, 30, 40, 50, 60, 70):
        r = vb.search(vb.Set.boot(dp, shift=shift), small)
        plc.append({"shift": shift, "gain_ce": r[r.signal == "ecys"].iloc[0].ce - r[r.signal == "none"].iloc[0].ce})
    plc = pd.DataFrame(plc)
    plc.to_csv(vb.OUT / "shiller_ecy_placebo.csv", index=False)
    log.append(f"placebo gains {plc.gain_ce.round(3).tolist()} vs real {gain:.3f}")
    (vb.OUT / "shiller_ecy_log.txt").write_text("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
