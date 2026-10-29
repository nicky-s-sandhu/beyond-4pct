"""Reproduce Kitces (2008) SAFEMAX by P/E10 band and Pfau (2011) "Can We Predict the Sustainable Withdrawal Rate
for New Retirees?" (Journal of Financial Planning 24 (8)): regression of the 30-year maximum withdrawal rate (MWR)
on the cyclically adjusted earnings yield (EY10 = 100/PE10), the 10-year average dividend yield (DY10) and the
10-year Treasury yield. Same conventions as repro_pfau_kitces.py: Shiller data, start-of-year fixed real withdrawals,
annual rebalancing, stocks with 10-year Treasuries.

    python scripts/repro_kitces_pfau2011.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import valuation as V  # noqa: E402

OUT = ROOT / "output" / "valuation"


def mwr(d, starts, stocks=0.6, safe="bonds"):
    S, B, _ = V.windows(d, starts, safe=safe)
    return V.safemax(stocks * S + (1 - stocks) * B) * 100


def ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    n, k = X1.shape
    r2 = 1 - resid.var() / y.var()
    return beta, r2, 1 - (1 - r2) * (n - 1) / (n - k)


def features(d, years):
    return np.column_stack([100 / d["cape_jan"].loc[years], d["div_yield_10y"].loc[years] * 100,
                            d["gs10_jan"].loc[years] * 100])


def main():
    d = V.load()
    last = d.index.max() - 29                          # last start with 30 years of returns (1993)
    # ---- Kitces (2008): SAFEMAX by starting P/E10 band, 60/40 stocks/bonds
    rows = []
    for label, end in (("data to 2007 (as in 2008)", 1978), (f"data to {d.index.max()}", last)):
        starts = list(range(1881, end + 1))
        m, pe = mwr(d, starts), d["cape_jan"].loc[starts].values
        for band, k in (("P/E10 below 12", pe < 12), ("P/E10 12-20", (pe >= 12) & (pe <= 20)), ("P/E10 above 20", pe > 20)):
            rows.append({"data": label, "band": band, "retirements": int(k.sum()), "SAFEMAX %": m[k].min(),
                         "worst start": np.array(starts)[k][np.argmin(m[k])], "median MWR %": np.median(m[k])})
    k8 = pd.DataFrame(rows)
    print("Kitces (2008) bands, 60/40 stocks/10-year Treasuries; Kitces's suggested start: 5.5% / 5.0% / 4.5%")
    print(k8.round(2).to_string(index=False))
    k8.to_csv(OUT / "kitces2008_bands.csv", index=False)

    # ---- Pfau (2011): fit on 1883-1980 starts (data through 2009), predict later starts
    fit_years = list(range(1883, 1981))
    rows = []
    for st in np.arange(0, 1.0001, 0.05):
        _, r2, adj = ols(features(d, fit_years), mwr(d, fit_years, stocks=st))
        rows.append({"stocks %": round(st * 100), "adj R2 %": adj * 100})
    r2t = pd.DataFrame(rows)
    print("\nPfau (2011) adjusted R2 by stock share (published: 53.4% at 0% stocks, max 74.5% at 55%)")
    print(r2t.set_index("stocks %").T.round(1).to_string())
    y = mwr(d, fit_years)
    beta, r2, adj = ols(features(d, fit_years), y)
    print(f"\n60/40 model: MWR = {beta[0]:.2f} + {beta[1]:.3f} EY10 + {beta[2]:.3f} DY10 + {beta[3]:.3f} Treasury yield"
          f"   adj R2 {adj * 100:.1f}%   SAFEMAX in fit {y.min():.2f}% ({fit_years[int(np.argmin(y))]})")
    later = list(range(1981, last + 1))
    pred_all = pd.Series(np.column_stack([np.ones(len(d)), features(d, d.index)]) @ beta, index=d.index)
    actual = pd.Series(mwr(d, later), index=later)
    comp = pd.DataFrame({"predicted MWR %": pred_all.loc[later], "actual MWR %": actual,
                         "CAPE": d["cape_jan"].loc[later]})
    print("\nOut-of-sample: starts after Pfau's data (predicted from January conditions vs what happened)")
    print(comp.round(2).to_string())
    print("\nPredictions for later starts (Pfau 2011 published: 2000 -> 2.7%, 2008 -> 1.5%, 2010 -> 1.8%)")
    print(pred_all.loc[[1982, 1992, 1996, 1999, 2000, 2008, 2010, 2020, 2022]].round(2).to_string())
    comp.to_csv(OUT / "pfau2011_out_of_sample.csv")
    r2t.to_csv(OUT / "pfau2011_r2.csv", index=False)


if __name__ == "__main__":
    main()
