"""100% stocks, switching the US part between an equal-weighted and a cap-weighted index by the Shiller ECY.

US equal weight: the equal-weighted return of the top quintile of US stocks by size (NYSE breakpoints, Ken French's
"Portfolios Formed on Size", equal-weighted monthly returns to Aug 2024, via a GitHub copy), compounded by
calendar year 1927-2023. Over 2004-2023 it tracked the S&P 500 Equal Weight index's yearly gap over the S&P 500
with correlation 0.87. 2024-2025: the S&P 500 Equal Weight index's total return (12.8%, 11.2%, chartrow.com).
Cap weight: the S&P 500 (Damodaran), as everywhere else in the study. International stocks stay 30%, cap-weighted.

Equal-weight share each January = clip(c + k_cheap * max(x, 0) + k_dear * min(x, 0), 0, 1), x = Shiller ECY vs its
median to date (stockrule's "ecys" signal); negative k_dear moves toward equal weight when stocks are dear.
All portfolios use the recommended plan's spending settings with the starting rate re-solved for 2% run-out on
reshuffled 1928-2025 history. Outputs output/ew_switch/*.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]
from bengen import alt, stockrule as sr  # noqa: E402
import valuation_best as vb  # noqa: E402
import etf_tests as et  # noqa: E402

OUT = ROOT / "output" / "ew_switch"
OUT.mkdir(parents=True, exist_ok=True)
FRENCH = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SP_EW_LATE = {2024: 0.128, 2025: 0.112}


def build_proxy(path):
    cols = ["date", "neg", "Lo30", "Med40", "Hi30", "Q1", "Q2", "Q3", "Q4", "Q5"] + [f"D{i}" for i in range(1, 11)]
    m = pd.read_csv(path, header=None, names=cols, skiprows=1)
    m = m[pd.to_numeric(m.date, errors="coerce").notna()]
    m["date"] = m.date.astype(int)
    m = m.set_index("date").astype(float) / 100
    y = m.index // 100
    n = pd.Series(y).value_counts()
    ann = (1 + m["Q5"]).groupby(y).prod() - 1
    ann = ann[ann.index.isin(n[n == 12].index)]
    out = pd.concat([ann, pd.Series(SP_EW_LATE)]).rename("us_ew")
    out.index.name = "year"
    out.to_csv(ROOT / "data/raw/us_equal_weight.csv", float_format="%.6f")
    return out


def frame():
    df = vb.frame("plan")
    ew = pd.read_csv(ROOT / "data/raw/us_equal_weight.csv").set_index("year")["us_ew"]
    df["S_ew"] = (1 - vb.INTL) * ew.reindex(df.index) + vb.INTL * df["intl"]
    return df


class Set(vb.Set):
    def __init__(self, df, idx):
        super().__init__(df, idx)
        self.E = df["S_ew"].values[idx]


def boot(df, years=None):
    d = df if years is None else df.loc[years[0]:years[1]]
    return Set(d, alt.bootstrap_index(len(d), vb.N, 30, vb.BLOCK, vb.SEED))


def ew_share(c, kc, kd, X):
    return np.clip(c + kc * np.maximum(X, 0) + kd * np.minimum(X, 0), 0, 1)


def score(st, R, rate=None):
    return et.evaluate(et.P0, R, st, rate)


def switch_R(st, c, kc, kd):
    e = ew_share(c, kc, kd, st.X["ecys"])
    return (1 - e) * st.S + e * st.E, e


GRID = [(c, kc, kd) for c, kc, kd in itertools.product((0, 0.25, 0.5, 0.75, 1), (-4, -2, -1, 0, 1, 2, 4),
                                                        (-4, -2, -1, 0, 1, 2, 4)) if not (kc == 0 and kd == 0)]


def search(st):
    rows = []
    for c, kc, kd in GRID:
        R, e = switch_R(st, c, kc, kd)
        rows.append({"c": c, "k_cheap": kc, "k_dear": kd, "avg_ew": e.mean() * 100, **score(st, R)})
    return pd.DataFrame(rows).sort_values("ce", ascending=False).reset_index(drop=True)


def label(r):
    return f"EW share {r.c:.0%} normal, {r.k_cheap:+g} cheap / {r.k_dear:+g} dear"


def main():
    if FRENCH:
        build_proxy(FRENCH)
    df = frame()
    log = []
    say = lambda *a: (print(*a, flush=True), log.append(" ".join(map(str, a))))

    # 1. Does ECY say anything about equal weight vs cap weight?
    h = df.loc[1928:2025]
    spread = (h["S_ew"] - h["S"]) / (1 - vb.INTL)          # US EW minus US cap weight
    x = h["x_ecys"]
    fwd3 = spread.rolling(3).sum().shift(-2)
    say("corr(ECY signal, EW-CW same year)", round(x.corr(spread), 3), " next 3 years", round(x.corr(fwd3), 3))
    for lab, msk in (("ECY well below median (x<-0.15)", x < -0.15), ("near median", x.abs() <= 0.15),
                     ("well above median (x>0.15)", x > 0.15)):
        say(f"  {lab}: {msk.sum()} years, mean EW-CW {spread[msk].mean() * 100:+.2f} pts/yr")
    geo = lambda s: ((1 + s).prod() ** (1 / len(s)) - 1) * 100
    say("US 1928-2025 geometric: cap weight", round(geo(h["stocks"]), 2), "equal weight", round(geo(h["stocks"] + spread), 2))

    full = boot(df)
    base = []
    for name, R, ew in (("100% stocks, all cap-weighted", full.S, 0.0), ("100% stocks, all equal-weighted", full.E, 1.0),
                        ("100% stocks, 50/50 EW and CW", 0.5 * full.S + 0.5 * full.E, 0.5)):
        base.append({"portfolio": name, "avg_ew": ew * 100, **score(full, R), "ran_out_at_6.5": score(full, R, 0.065)["ran_out"]})
    W = sr.shares(et.ECY, full.X["ecys"])
    for name, R in (("Fixed 80% stocks (plan)", 0.8 * full.S + 0.2 * full.B),
                    ("ECY stock/bond rule, 50-100%", W * full.S + (1 - W) * full.B)):
        base.append({"portfolio": name, "avg_ew": 0.0, **score(full, R), "ran_out_at_6.5": score(full, R, 0.065)["ran_out"]})

    res = search(full)
    res.to_csv(OUT / "search.csv", index=False)
    best = res.iloc[0]
    toward_ew_dear = res[(res.k_dear < 0)].iloc[0]
    toward_ew_cheap = res[(res.k_cheap > 0) & (res.k_dear >= 0)].iloc[0]
    for tag, r in (("best switch", best), ("best that goes EW when dear", toward_ew_dear),
                   ("best that goes EW when cheap", toward_ew_cheap)):
        Rr, _ = switch_R(full, r.c, r.k_cheap, r.k_dear)
        base.append({"portfolio": f"{tag}: {label(r)}", "avg_ew": r.avg_ew, **score(full, Rr),
                     "ran_out_at_6.5": score(full, Rr, 0.065)["ran_out"]})
    tab = pd.DataFrame(base)
    tab.to_csv(OUT / "comparison.csv", index=False)
    say(tab[["portfolio", "rate", "ce", "ran_out_at_6.5", "typ_1_10", "p10_year", "median_final", "avg_ew"]].round(2).to_string())

    # 2. split sample: choose the switch on one half, test on the other, against the better of all-CW / all-EW
    halves = {"1928-1976": (1928, 1976), "1977-2025": (1977, 2025)}
    sets = {k: boot(df, v) for k, v in halves.items()}
    split = []
    for fit, test in (("1928-1976", "1977-2025"), ("1977-2025", "1928-1976")):
        r = search(sets[fit]).iloc[0]
        f_cw, f_ew = score(sets[fit], sets[fit].S), score(sets[fit], sets[fit].E)
        static = "EW" if f_ew["ce"] > f_cw["ce"] else "CW"
        t = sets[test]
        Rs, _ = switch_R(t, r.c, r.k_cheap, r.k_dear)
        o_sw, o_st = score(t, Rs), score(t, t.E if static == "EW" else t.S)
        split.append({"fit": fit, "test": test, "switch": label(r), "static_choice": static,
                      "switch_rate_out": o_sw["rate"], "switch_ce_out": o_sw["ce"],
                      "static_rate_out": o_st["rate"], "static_ce_out": o_st["ce"]})
        say(f"split {fit}->{test}: {label(r)} out {o_sw['rate']:.2f}/{o_sw['ce']:.2f} vs all-{static} {o_st['rate']:.2f}/{o_st['ce']:.2f}")
    pd.DataFrame(split).to_csv(OUT / "split.csv", index=False)
    (OUT / "log.txt").write_text("\n".join(log) + "\n")


if __name__ == "__main__":
    main()
