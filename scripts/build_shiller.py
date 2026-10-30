"""Build data/raw/shiller_annual.csv from Robert Shiller's monthly stock market data.

Source: Shiller, "U.S. Stock Markets 1871-Present and CAPE Ratio" (ie_data.xls, Yale), copy dated Aug 2023 taken
from the datasets/s-and-p-500 repository on GitHub (archive/shiller.xls), saved as
data/external/shiller/ie_data_2023-08.xls (not committed). Short-term rates are not in that file: bills come from the
Jorda-Schularick-Taylor Macrohistory Database R6 (US bill_rate) through 2020 and Damodaran T-bills after.

All return series run January to January, matching the January CAPE used to make decisions:
  year y = holding period from January of year y to January of year y + 1.

    python scripts/build_shiller.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/tmp/claude-0/xlrd")      # xlrd from GitHub when pip is unavailable
XLS = ROOT / "data" / "external" / "shiller" / "ie_data_2023-08.xls"
JST = ROOT / "data" / "external" / "JSTdatasetR6.csv"
OUT = ROOT / "data" / "raw" / "shiller_annual.csv"

COLS = ["date", "P", "D", "E", "CPI", "fraction", "GS10", "real_price", "real_div", "real_tr_price", "real_earn",
        "scaled_earn", "CAPE", "_a", "TR_CAPE", "_b", "excess_cape_yield", "bond_month_ret", "real_bond_tr",
        "stock_10y_real", "bond_10y_real", "excess_10y"]


def monthly():
    d = pd.read_excel(XLS, "Data", header=None, skiprows=8, names=COLS)
    d = d[pd.to_numeric(d["date"], errors="coerce").notna()].copy()
    d["date"] = d["date"].astype(float)
    d["year"] = np.floor(d["date"] + 1e-9).astype(int)
    d["month"] = np.round((d["date"] - d["year"]) * 100).astype(int)
    return d


def intl_extended():
    """Developed ex-US stocks in USD, calendar years: the repo's series (JST GDP-weighted 1928-69, MSCI World ex USA
    1970+, see build_intl.py) extended back to 1871 with the same JST method (15 countries, local total return in USD,
    weighted by prior-year real GDP; countries without data in a year are skipped)."""
    d = pd.read_csv(JST, usecols=["year", "iso", "eq_tr", "xrusd", "rgdpmad", "pop"])
    d = d[d.iso != "USA"].sort_values(["iso", "year"])
    g = d.groupby("iso")
    d["xr_prev"], d["w_prev"] = g.xrusd.shift(), g.rgdpmad.shift() * g["pop"].shift()
    d["usd_ret"] = (1 + d.eq_tr) * d.xr_prev / d.xrusd - 1
    d = d.dropna(subset=["usd_ret", "w_prev"])
    d = d[d.year < 1928]
    early = d.groupby("year").apply(lambda x: (x.w_prev / x.w_prev.sum() * x.usd_ret).sum(), include_groups=False)
    n = d.groupby("year").size()
    later = pd.read_csv(ROOT / "data" / "raw" / "intl_stocks.csv").set_index("year")["intl"] / 100
    return pd.concat([early, later]).sort_index(), n


def annual():
    m = monthly()
    jan = m[m["month"] == 1].set_index("year")
    nxt = jan.shift(-1)
    out = pd.DataFrame(index=jan.index)
    out["cape_jan"] = jan["CAPE"]
    out["gs10_jan"] = jan["GS10"] / 100
    out["div_yield_jan"] = jan["D"] / jan["P"]
    out["div_yield_10y"] = out["div_yield_jan"].rolling(10).mean()          # Pfau (2011): 10-year moving average
    out["inflation"] = nxt["CPI"] / jan["CPI"] - 1
    out["real_stocks"] = nxt["real_tr_price"] / jan["real_tr_price"] - 1
    out["real_bonds"] = nxt["real_bond_tr"] / jan["real_bond_tr"] - 1
    out["stocks"] = (1 + out["real_stocks"]) * (1 + out["inflation"]) - 1
    out["bonds"] = (1 + out["real_bonds"]) * (1 + out["inflation"]) - 1
    jst = pd.read_csv(JST)
    bills = jst[jst["iso"] == "USA"].set_index("year")["bill_rate"]
    dam = pd.read_csv(ROOT / "data" / "raw" / "damodaran_returns.csv").set_index("year")["tbill_3m"] / 100
    out["bills"] = bills.reindex(out.index).fillna(dam.reindex(out.index))
    out["real_bills"] = (1 + out["bills"]) / (1 + out["inflation"]) - 1
    # international stocks: calendar-year USD returns (Dec-Dec), used against Jan-Jan inflation (one month apart)
    intl, _ = intl_extended()
    out["intl"] = intl.reindex(out.index)
    out["real_intl"] = (1 + out["intl"]) / (1 + out["inflation"]) - 1
    return out.dropna(subset=["inflation"])


def main():
    a = annual()
    a.round(8).to_csv(OUT, index_label="year")
    print(OUT, a.index.min(), a.index.max(), len(a))
    print(a.loc[[1871, 1921, 1929, 1966, 2000, 2022]].round(4).to_string())


if __name__ == "__main__":
    main()
