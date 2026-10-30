"""Shiller's Excess CAPE Yield each January -> data/raw/shiller_ecy_jan.csv

1881-2023: the 'Excess CAPE Yield' column of Shiller's ie_data.xls (August 2023 edition, data/external/shiller/).
Shiller defines it as 1/CAPE - (GS10 - annualised CPI inflation over the previous 10 years); recomputing it from the
same sheet reproduces his column exactly (checked below), so 2024-2026 use that formula with:
  CAPE: data/raw/shiller_cape_jan.csv (equal to Shiller's for 2022-2023)
  GS10: January averages 4.06%, 4.63%, 4.21% (FRED GS10, via multpl.com)
  CPI-U (NSA, 1982-84=100), January: 2014 233.916, 2015 233.707, 2016 236.916, 2024 308.417, 2025 317.671,
        2026 325.252 (BLS, as tabulated by Idaho Dept. of Labor, 2026-CPI.pdf)
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parents[1]
CPI_JAN = {2014: 233.916, 2015: 233.707, 2016: 236.916, 2024: 308.417, 2025: 317.671, 2026: 325.252}
GS10_JAN = {2024: 4.06, 2025: 4.63, 2026: 4.21}


def main():
    s = xlrd.open_workbook(ROOT / "data/external/shiller/ie_data_2023-08.xls").sheet_by_name("Data")
    rows = []
    for r in range(8, s.nrows):
        v = s.row_values(r)
        try:
            d = float(v[0])
        except (TypeError, ValueError):
            continue
        if round((d - int(d)) * 100) == 1:
            rows.append((int(d), v[12], v[16], v[6], v[4]))
    d = pd.DataFrame(rows, columns=["year", "cape", "ecy", "gs10", "cpi"]).set_index("year")
    d = d.replace(["", "NA"], np.nan).astype(float)
    rep = 1 / d.cape - (d.gs10 / 100 - ((d.cpi / d.cpi.shift(10)) ** 0.1 - 1))
    assert (rep - d.ecy).abs().max() < 1e-12, "formula does not reproduce Shiller's column"
    cape = pd.read_csv(ROOT / "data/raw/shiller_cape_jan.csv").set_index("year")["cape_jan"]
    out = d[["ecy"]].dropna().assign(source="Shiller ie_data.xls (Aug 2023)")
    for y in (2024, 2025, 2026):
        infl10 = (CPI_JAN[y] / CPI_JAN[y - 10]) ** 0.1 - 1
        out.loc[y] = [1 / cape[y] - (GS10_JAN[y] / 100 - infl10), "Shiller's formula, updated inputs"]
    out.index.name = "year"
    out.to_csv(ROOT / "data/raw/shiller_ecy_jan.csv", float_format="%.6f")
    print(out.tail(6))


if __name__ == "__main__":
    main()
