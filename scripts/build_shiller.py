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
    return out.dropna(subset=["inflation"])


def main():
    a = annual()
    a.round(8).to_csv(OUT, index_label="year")
    print(OUT, a.index.min(), a.index.max(), len(a))
    print(a.loc[[1871, 1921, 1929, 1966, 2000, 2022]].round(4).to_string())


if __name__ == "__main__":
    main()
