"""Build an annual developed-markets ex-US stock return series in USD.

Final series `intl` = JST build for 1928-1969, MSCI World ex USA for 1970-2025.
MSCI is the cap-weighted market benchmark; JST is the only free long history.
(JST's Japan returns look smoothed after 1970 -- e.g. 1990 -13% vs TOPIX ~-40%
-- so we switch to MSCI as soon as it exists.)

JST build: Jorda-Schularick-Taylor Macrohistory Database (R6), 17 non-US
           countries (Canada and Ireland have no equity data, leaving 15).
           Each country's local total return is converted to USD with the JST
           exchange rate (local currency per USD), then weighted by the prior
           year's real GDP (Maddison GDP per capita x population, so all
           countries are in the same PPP units). A country is skipped in any
           year its return or exchange rate is missing (e.g. Japan 1946-47),
           which flatters the series a little -- see README.
           Patch: Germany 1949 uses the official Deutsche Mark parity
           (3.33 -> 4.20 per USD) because JST's 1948 rate predates the
           currency reform and turns +137% local into +702% in USD.
MSCI World ex USA: annual USD total returns, 1970-2025 (upmyinterest.com table;
cross-checked against MSCI's official EAFE factsheet for 2012-2025, within ~2pp
per year, the gap being Canada).

Licence: the JST data, and so data/raw/intl_stocks.csv, are CC BY-NC-SA 4.0
(non-commercial, share alike, attribution). See data/raw/LICENSE-intl_stocks.md.

Usage:
    python scripts/build_intl.py [path/to/JSTdatasetR6.csv]
JST data: https://www.macrohistory.net/database/
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JST = ROOT / "data" / "external" / "JSTdatasetR6.csv"
OUT = ROOT / "data" / "raw" / "intl_stocks.csv"

# (start-of-year, end-of-year) local currency per USD, replacing JST values
FX_OVERRIDES = {("DEU", 1949): (3.33, 4.20)}

# MSCI World ex USA, USD total return, %
MSCI_WXUS = {
    1970: -13.4, 1971: 33.3, 1972: 40.4, 1973: -10.7, 1974: -18.5, 1975: 32.8, 1976: 3.6, 1977: 17.5,
    1978: 33.1, 1979: 10.9, 1980: 25.4, 1981: -2.5, 1982: -0.3, 1983: 24.8, 1984: 3.5, 1985: 51.4,
    1986: 65.8, 1987: 24.6, 1988: 27.8, 1989: 11.4, 1990: -22.8, 1991: 12.4, 1992: -11.9, 1993: 32.6,
    1994: 7.6, 1995: 11.8, 1996: 7.2, 1997: 2.6, 1998: 19.1, 1999: 28.3, 2000: -13.2, 2001: -21.2,
    2002: -15.5, 2003: 40.0, 2004: 20.8, 2005: 15.0, 2006: 26.2, 2007: 12.9, 2008: -43.2, 2009: 34.4,
    2010: 9.4, 2011: -11.8, 2012: 17.0, 2013: 21.6, 2014: -3.9, 2015: -2.6, 2016: 3.3, 2017: 24.8,
    2018: -13.6, 2019: 23.2, 2020: 8.1, 2021: 13.2, 2022: -13.8, 2023: 18.6, 2024: 4.7, 2025: 31.9,
}
MSCI_FROM = 1970

# Stress version: fill country-years the JST build has to skip with pessimistic
# USD returns, so missing wartime wipeouts can't flatter the series.
#   Japan 1946-47: local stocks assumed flat; yen 6.9 -> 180 -> 238 per USD.
#   Germany 1945:  assume a 75% USD loss (occupation; official data missing).
#   Netherlands 1940-44, Norway 1940-45: assume -25% a year (occupation).
STRESS_FILL = {("JPN", 1946): 6.9 / 180 - 1, ("JPN", 1947): 180 / 238 - 1, ("DEU", 1945): -0.75,
               **{("NLD", y): -0.25 for y in range(1940, 1945)},
               **{("NOR", y): -0.25 for y in range(1940, 1946)}}


def build(jst_path: Path) -> pd.DataFrame:
    d = pd.read_csv(jst_path, usecols=["year", "iso", "eq_tr", "xrusd", "rgdpmad", "pop"])
    d = d[d.iso != "USA"].sort_values(["iso", "year"])
    g = d.groupby("iso")
    d["xr_prev"] = g.xrusd.shift()
    d["w_prev"] = g.rgdpmad.shift() * g["pop"].shift()  # prior-year real GDP, PPP units
    for (iso, yr), (xr0, xr1) in FX_OVERRIDES.items():
        m = (d.iso == iso) & (d.year == yr)
        d.loc[m, ["xr_prev", "xrusd"]] = [xr0, xr1]
    d["usd_ret"] = (1 + d.eq_tr) * d.xr_prev / d.xrusd - 1
    d["usd_stress"] = d.usd_ret
    for (iso, yr), r in STRESS_FILL.items():
        d.loc[(d.iso == iso) & (d.year == yr), "usd_stress"] = r
    stress_rows = d.dropna(subset=["usd_stress", "w_prev"])
    stress_rows = stress_rows[(stress_rows.year >= 1928) & (stress_rows.year <= 2020)]
    stress = stress_rows.groupby("year").apply(
        lambda x: (x.w_prev / x.w_prev.sum() * x.usd_stress).sum() * 100, include_groups=False)
    d = d.dropna(subset=["usd_ret", "w_prev"])
    d = d[(d.year >= 1928) & (d.year <= 2020)]

    def agg(x):
        w = x.w_prev / x.w_prev.sum()
        return pd.Series({"intl_gdp": (w * x.usd_ret).sum() * 100,
                          "intl_equal": x.usd_ret.mean() * 100,
                          "n_countries": len(x),
                          "largest": x.loc[w.idxmax(), "iso"] + f" {w.max():.0%}"})

    out = d.groupby("year").apply(agg, include_groups=False).reset_index()
    out = out.merge(pd.DataFrame({"year": list(MSCI_WXUS), "msci_wxus": list(MSCI_WXUS.values())}),
                    on="year", how="outer").sort_values("year")
    out["intl"] = out.intl_gdp.where(out.year < MSCI_FROM, out.msci_wxus)
    out["intl_stress"] = out.year.map(stress).where(out.year < MSCI_FROM, out.msci_wxus)
    out["source"] = ["JST R6 (GDP-wtd)" if y < MSCI_FROM else "MSCI World ex USA" for y in out.year]
    cols = ["intl", "intl_stress", "intl_gdp", "intl_equal"]
    out[cols] = out[cols].round(2)
    return out[["year", "intl", "intl_stress", "source", "intl_gdp", "intl_equal", "msci_wxus", "n_countries", "largest"]]

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JST
    df = build(path)
    df.to_csv(OUT, index=False)
    print(df.to_string(index=False))
