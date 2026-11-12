"""Annual trend-following proxy from the Jorda-Schularick-Taylor Macrohistory Database (R6), 1871-2020.

Markets: each country's stocks and long government bonds, as local excess returns over local bills (what a futures
position earns). Each year, go long a market whose excess return over the previous 12 months was positive and short
it otherwise, sized to 40% ex-ante volatility (trailing 10-year standard deviation, at least 5 years), averaged
across markets (Hurst, Ooi and Pedersen's construction, at annual instead of monthly frequency). The book is scaled
each year to 10% ex-ante volatility using its own trailing 20-year volatility, then T-bill collateral is added and
a 1%/yr fee-and-cost drag subtracted. Output: data/raw/trend_proxy.csv (year, trend_excess, trend = nominal USD
return incl. US bill collateral, net of fees).

Annual rebalancing misses trends that turn within a year (2008, for one), so this likely understates a monthly
managed-futures fund.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEE = 0.01


def main():
    j = pd.read_csv(ROOT / "data/external/JSTdatasetR6.csv", encoding="utf-8-sig")
    ex = {}
    for iso, g in j.groupby("iso"):
        g = g.set_index("year")
        for a in ("eq_tr", "bond_tr"):
            ex[f"{iso}_{a[:-3]}"] = g[a] - g["bill_rate"]
    X = pd.DataFrame(ex).sort_index()
    vol = X.rolling(10, min_periods=5).std().shift(1)
    sig = np.sign(X.shift(1))
    pos = sig * 0.40 / vol
    raw = (pos * X).mean(axis=1, skipna=True)
    n = (pos * X).notna().sum(axis=1)
    raw[n < 6] = np.nan
    scale = 0.10 / raw.rolling(20, min_periods=10).std().shift(1)
    tex = (raw * scale).dropna()
    us_bill = j[j.iso == "USA"].set_index("year")["bill_rate"]
    out = pd.DataFrame({"trend_excess": tex - FEE, "trend": tex - FEE + us_bill.reindex(tex.index), "markets": n.reindex(tex.index)})
    out.index.name = "year"
    out.to_csv(ROOT / "data/raw/trend_proxy.csv", float_format="%.6f")
    print(out.describe().round(3))
    print(out.loc[[1929, 1930, 1931, 1937, 1973, 1974, 2000, 2001, 2002, 2008, 2014, 2018, 2020]].round(3))
    print("excess return mean (net) 1928-2020", out.trend_excess.loc[1928:].mean().round(4),
          "since 1985", out.trend_excess.loc[1985:].mean().round(4))


if __name__ == "__main__":
    main()
