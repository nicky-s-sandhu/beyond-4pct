"""100% stocks: move the US part toward equal weight when stocks are DEAR (Shiller ECY below its median).

Rules: EW share = clip(c + k_cheap * max(x,0) + k_dear * min(x,0), 0, 1) with k_dear < 0 (more EW as ECY falls below its
median) and k_cheap <= 0; plus on/off switches: all EW when x < t, else all cap weight. Same data and plan settings as
ew_switch.py. Also: by-era results and the ECY stock/bond rule combined with these switches. Outputs output/ew_switch/dear_*.
"""
import itertools
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path[:0] = [str(Path(__file__).resolve().parent)]
import ew_switch as ew  # noqa: E402
import etf_tests as et  # noqa: E402
from bengen import stockrule as sr  # noqa: E402

RAMPS = [(c, kc, kd) for c, kc, kd in itertools.product((0, 0.25, 0.5), (0, -1, -2), (-0.5, -1, -2, -4))]
STEPS = (0.0, -0.1, -0.2, -0.3)


def rules():
    out = [("All cap-weighted", lambda X: np.zeros_like(X)), ("All equal-weighted", lambda X: np.ones_like(X))]
    for c, kc, kd in RAMPS:
        out.append((f"ramp: {c:.0%} EW normal, {kd:g} per unit dear, {kc:g} cheap",
                    lambda X, c=c, kc=kc, kd=kd: ew.ew_share(c, kc, kd, X)))
    for t in STEPS:
        out.append((f"switch: all EW when ECY signal < {t:g}", lambda X, t=t: (X < t).astype(float)))
    return out


def run(st, combo=False):
    W = sr.shares(et.ECY, st.X["ecys"]) if combo else 1.0
    rows = []
    for name, f in rules():
        e = f(st.X["ecys"])
        R = W * ((1 - e) * st.S + e * st.E) + (1 - W) * st.B
        s = ew.score(st, R)
        rows.append({"rule": name, "avg_ew": float(np.mean(e)) * 100, **s, "ran_out_at_6.5": ew.score(st, R, 0.065)["ran_out"]})
    return pd.DataFrame(rows)


def main():
    df = ew.frame()
    x = df["x_ecys"].loc[1928:2025]
    print("years with signal < 0 / -0.1 / -0.2:", [(x < t).sum() for t in (0, -0.1, -0.2)], "of", len(x))
    sets = {"1928-2025": ew.boot(df), "1928-1976": ew.boot(df, (1928, 1976)), "1977-2025": ew.boot(df, (1977, 2025)),
            "1995-2025": ew.boot(df, (1995, 2025))}
    allr = []
    for sn, st in sets.items():
        for combo in (False, True):
            r = run(st, combo).assign(set=sn, base="ECY stock/bond rule" if combo else "100% stocks")
            allr.append(r)
    d = pd.concat(allr)
    d.to_csv(ew.OUT / "dear_all.csv", index=False)
    piv = d.pivot_table(index=["base", "rule"], columns="set", values="rate").round(2)
    ce = d.pivot_table(index=["base", "rule"], columns="set", values="ce").round(2)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(piv.to_string()); print(ce.to_string())
    m = d[(d.set == "1928-2025")][["base", "rule", "avg_ew", "rate", "ce", "ran_out_at_6.5", "median_final"]]
    print(m.round(2).to_string())
    # history: spread in dear years by era
    h = df.loc[1928:2025]
    spread = (h["S_ew"] - h["S"]) / (1 - ew.vb.INTL)
    for a, b in ((1928, 1960), (1961, 1994), (1995, 2010), (2011, 2025)):
        s = spread.loc[a:b]; xx = x.loc[a:b]
        print(f"{a}-{b}: dear years {int((xx < 0).sum())}, EW-CW in dear years {s[xx < 0].mean() * 100:+.2f}, in other years {s[xx >= 0].mean() * 100:+.2f}")
    print((pd.DataFrame({"x": x, "EW-CW %": spread * 100}).loc[[1929, 1937, 1966, 1973, 1999, 2000, 2001, 2002, 2007, 2018, 2021, 2022, 2023, 2024, 2025]]).round(2))


if __name__ == "__main__":
    main()
