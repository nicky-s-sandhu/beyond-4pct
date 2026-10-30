"""Search for the best valuation-based stock rule, judged inside the recommended withdrawal plan.

For each stock rule (bengen.stockrule.Rule), the plan's starting rate is raised until 2% of reshuffled-history
retirements run out; the rule is then scored by the smooth-spending score (CE, gamma 3, couple weights) at that
rate. All spending settings other than the starting rate stay at the recommended plan's.

Tests against overfitting:
  split  - choose the best rule on reshuffled history built only from 1928-1976, test it on history built only
           from 1977-2025, and the other way round; compare with the best fixed mix chosen the same way
  placebo- shift the valuation signal by 20-70 years (keeps its persistence, breaks its link to returns), search
           again; the gain a rule finds there is what search alone can produce
  long   - repeat on 1881-2022 (Shiller, with JST international stocks before 1928)

Usage: python3 scripts/valuation_best.py   (about 10 minutes); outputs in output/valuation/best_*
"""
from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from bengen import alt, data, vec, stockrule as sr          # noqa: E402
from app import model                                       # noqa: E402

OUT = ROOT / "output" / "valuation"
OUT.mkdir(parents=True, exist_ok=True)
P = model.to_params(model.RECOMMENDED)
WTS = vec.survival_weights(30, who="couple")
INTL = 0.3
N, BLOCK, SEED = 5000, 10, 7


def frame(which="plan"):
    if which == "plan":
        df = data.load(intl_series="intl")
        df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
        sig = sr.signals(df["inflation"])
    else:
        sh = pd.read_csv(ROOT / "data" / "raw" / "shiller_annual.csv").set_index("year").loc[1881:2022]
        df = pd.DataFrame({"stocks": sh["stocks"], "intl": sh["intl"], "inflation": sh["inflation"],
                           "bonds": 0.5 * sh["bills"] + 0.5 * sh["bonds"]})
        sig = sr.signals()
    df["S"] = (1 - INTL) * df["stocks"] + INTL * df["intl"]
    for k in ("cape", "ecy", "none"):
        df[f"x_{k}"] = sig[f"x_{k}"].reindex(df.index).fillna(0.0)
    return df


class Set:
    """Reshuffled-history retirements (or historical windows) with their signals."""
    def __init__(self, df, idx):
        self.S, self.B, self.I = (df[k].values[idx] for k in ("S", "bonds", "inflation"))
        self.X = {k: df[f"x_{k}"].values[idx] for k in ("cape", "ecy", "none")}

    @classmethod
    def boot(cls, df, years=None, n=N, seed=SEED, shift=0):
        d = df if years is None else df.loc[years[0]:years[1]]
        if shift:
            d = d.copy()
            for k in ("cape", "ecy"):
                d[f"x_{k}"] = np.roll(d[f"x_{k}"].values, shift)
        return cls(d, alt.bootstrap_index(len(d), n, 30, BLOCK, seed))

    @classmethod
    def hist(cls, df):
        n = len(df) - 29
        return cls(df, np.arange(n)[:, None] + np.arange(30)[None, :])


def score(rule, st: Set, rate=None):
    W = sr.shares(rule, st.X[rule.signal])
    r = sr.rate_at(P, W, st.S, st.B, st.I) if rate is None else rate
    out = sr.simulate(replace(P, rate=r), W, st.S, st.B, st.I)
    m = vec.metrics(replace(P, rate=r), {**out}, weights=WTS)
    return {"rate": r * 100, "ce": m["ce"], "ran_out": out["depleted"].mean() * 100,
            "typ_1_10": m["typical_1_10"], "typ_avg": m["typical_avg"], "p10_year": m["p10_year"],
            "cut30": m["severe_plus_share"] * 100, "median_final": m["median_final"],
            "avg_stocks": W.mean() * 100}


def grid(signals=("cape", "ecy"), speeds=(1.0,), lo_min=0.0):
    rules = [sr.Rule("none", c) for c in np.arange(0.4, 1.001, 0.05)]
    for sig, c, kc, kd, lo, sp in itertools.product(signals, (0.5, 0.6, 0.7, 0.8, 0.9, 1.0), (0, 0.5, 1, 2, 4),
                                                    (0, 0.5, 1, 2, 4), (0.0, 0.25, 0.5), speeds):
        if lo < lo_min or lo > c or (kc == 0 and kd == 0) or (kd == 0 and lo > 0) or (kc == 0 and c == 1.0):
            continue
        rules.append(sr.Rule(sig, round(c, 2), kc, kd, lo, 1.0, sp))
    return rules


def search(st: Set, rules, key="ce"):
    rows = [{**r.as_dict(), "label": r.label(), **score(r, st)} for r in rules]
    return pd.DataFrame(rows).sort_values(key, ascending=False).reset_index(drop=True)


def refine(st: Set, top: pd.DataFrame, k=15):
    """Add slower adjustment speeds and finer steps around the best rules."""
    seen, rules = set(), []
    for _, r in top.head(k).iterrows():
        if r.signal == "none":
            continue
        for sp, dc, dkc, dkd in itertools.product((1.0, 0.5, 0.25), (-0.05, 0, 0.05), (0.75, 1, 1.5), (0.75, 1, 1.5)):
            rule = sr.Rule(r.signal, round(min(max(r.c + dc, 0.3), 1.0), 2), r.k_cheap * dkc, r.k_dear * dkd,
                           r.lo, r.hi, sp)
            if rule not in seen:
                seen.add(rule)
                rules.append(rule)
    return search(st, rules)


def to_rule(row):
    return sr.Rule(row["signal"], row["c"], row["k_cheap"], row["k_dear"], row["lo"], row["hi"], row["speed"])


def main():
    log = []
    say = lambda *a: (print(*a, flush=True), log.append(" ".join(str(x) for x in a)))
    df = frame("plan")
    full = Set.boot(df)
    hist = Set.hist(df)

    # 1. full search
    res = search(full, grid())
    res = pd.concat([res, refine(full, res)]).drop_duplicates("label").sort_values("ce", ascending=False)
    res.to_csv(OUT / "best_search.csv", index=False)
    fixed = res[res.signal == "none"].reset_index(drop=True)
    say("Best fixed:", fixed.iloc[0][["label", "rate", "ce", "typ_1_10"]].to_dict())
    say("Fixed 80% (the plan):", fixed[np.isclose(fixed.c, 0.8)].iloc[0][["rate", "ce", "typ_1_10"]].to_dict())
    for sig in ("cape", "ecy"):
        say(f"Best {sig}:", res[res.signal == sig].iloc[0][["label", "rate", "ce", "typ_1_10", "avg_stocks"]].to_dict())
    b50 = res[(res.signal != "none") & (res.lo >= 0.5)]
    say("Best with stocks never below 50%:", b50.iloc[0][["label", "rate", "ce", "typ_1_10"]].to_dict())

    # 2. split-sample
    halves = {"early": (1928, 1976), "late": (1977, 2025)}
    sets = {h: Set.boot(df, y) for h, y in halves.items()}
    split = []
    for fit, test in (("early", "late"), ("late", "early")):
        r_fit = search(sets[fit], grid())
        r_fit = pd.concat([r_fit, refine(sets[fit], r_fit)]).sort_values("ce", ascending=False)
        for kind, sub in (("fixed", r_fit[r_fit.signal == "none"]), ("cape", r_fit[r_fit.signal == "cape"]),
                          ("ecy", r_fit[r_fit.signal == "ecy"]),
                          ("cape >=50%", r_fit[(r_fit.signal == "cape") & (r_fit.lo >= 0.5)])):
            rule = to_rule(sub.iloc[0])
            ins, oos = score(rule, sets[fit]), score(rule, sets[test])
            split.append({"fit": fit, "test": test, "kind": kind, "rule": rule.label(),
                          "rate_in": ins["rate"], "ce_in": ins["ce"], "rate_out": oos["rate"], "ce_out": oos["ce"],
                          "typ_out": oos["typ_1_10"]})
            say("split", fit, "->", test, kind, rule.label(), f"in {ins['rate']:.2f}/{ins['ce']:.2f}",
                f"out {oos['rate']:.2f}/{oos['ce']:.2f}")
    pd.DataFrame(split).to_csv(OUT / "best_split.csv", index=False)

    # 3. placebo: valuation signal shifted in time
    best_fixed_ce = fixed.iloc[0]["ce"]
    plc = []
    small = [r for r in grid() if r.signal != "ecy"]
    for shift in (20, 30, 40, 50, 60, 70):
        st = Set.boot(df, shift=shift)
        r = search(st, small)
        bf = r[r.signal == "none"].iloc[0]
        bc = r[r.signal == "cape"].iloc[0]
        plc.append({"shift": shift, "best_fixed_ce": bf.ce, "best_rule_ce": bc.ce, "gain_ce": bc.ce - bf.ce,
                    "gain_rate": bc.rate - bf.rate, "rule": bc.label})
        say("placebo", shift, f"gain CE {bc.ce - bf.ce:+.3f} rate {bc.rate - bf.rate:+.2f}", bc.label)
    pd.DataFrame(plc).to_csv(OUT / "best_placebo.csv", index=False)
    real_small = search(full, small)
    say("real (same grid) gain CE", f"{real_small[real_small.signal=='cape'].iloc[0].ce - real_small[real_small.signal=='none'].iloc[0].ce:+.3f}")

    # 4. long history 1881-2022
    dl = frame("long")
    full_l = Set.boot(dl)
    rl = search(full_l, grid())
    rl = pd.concat([rl, refine(full_l, rl)]).drop_duplicates("label").sort_values("ce", ascending=False)
    rl.to_csv(OUT / "best_search_long.csv", index=False)
    say("LONG best fixed:", rl[rl.signal == "none"].iloc[0][["label", "rate", "ce"]].to_dict())
    for sig in ("cape", "ecy"):
        say(f"LONG best {sig}:", rl[rl.signal == sig].iloc[0][["label", "rate", "ce", "avg_stocks"]].to_dict())
    # cross-check: 1928-2025 winners on long history and vice versa
    cross = []
    for name, src, dst, dst_name in (("plan winner", res, full_l, "long"), ("long winner", rl, full, "plan")):
        for sig in ("none", "cape", "ecy"):
            rule = to_rule(src[src.signal == sig].iloc[0])
            s = score(rule, dst)
            cross.append({"from": name, "on": dst_name, "rule": rule.label(), **s})
            say("cross", name, "on", dst_name, rule.label(), f"rate {s['rate']:.2f} ce {s['ce']:.2f}")
    pd.DataFrame(cross).to_csv(OUT / "best_cross.csv", index=False)

    # 5. historical retirements at the rate set by reshuffled history
    histrows = []
    cands = {"Fixed 80% (plan)": sr.Rule("none", 0.8)}
    for sig in ("cape", "ecy"):
        cands[f"best {sig}"] = to_rule(res[res.signal == sig].iloc[0])
    cands["best cape, >=50%"] = to_rule(res[(res.signal == "cape") & (res.lo >= 0.5)].iloc[0])
    for name, rule in cands.items():
        b = score(rule, full)
        h = score(rule, hist, rate=b["rate"] / 100)
        histrows.append({"name": name, "rule": rule.label(), **{f"boot_{k}": v for k, v in b.items()},
                         **{f"hist_{k}": v for k, v in h.items()}})
    pd.DataFrame(histrows).to_csv(OUT / "best_candidates.csv", index=False)
    (OUT / "best_log.txt").write_text("\n".join(log) + "\n")
    json.dump({k: v.as_dict() for k, v in cands.items()}, open(OUT / "best_rules.json", "w"), indent=1)


if __name__ == "__main__":
    main()
