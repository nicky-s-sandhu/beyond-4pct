"""Data loading for the Bengen (1994) replication.

Two sources are combined into one annual table:

* Asset returns: Aswath Damodaran (NYU Stern), "Historical Returns on Stocks,
  Bonds and Bills" -- S&P 500 total return and 10-year US Treasury bond total
  return, 1928 onward.
* Inflation: US CPI-U (not seasonally adjusted), December-to-December change.

`download()` fetches the original files. If you can't reach them, the
snapshot CSVs in data/raw/ are used instead.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

DAMODARAN_XLS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls"
FRED_CPI_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS"

RETURNS_CSV = RAW / "damodaran_returns.csv"
CPI_CSV = RAW / "cpi_dec_dec.csv"
INTL_CSV = RAW / "intl_stocks.csv"  # built by scripts/build_intl.py


# ---------------------------------------------------------------- download
def _get(url: str) -> bytes:
    import requests

    r = requests.get(url, timeout=60, headers={"User-Agent": "bengen-replication/0.1"})
    r.raise_for_status()
    return r.content


def _parse_damodaran(xls_bytes: bytes) -> pd.DataFrame:
    """Find the annual-returns block in histretSP.xls, whatever sheet it's on."""
    sheets = pd.read_excel(io.BytesIO(xls_bytes), sheet_name=None, header=None)
    for name, df in sheets.items():
        for i in range(min(len(df), 40)):
            row = df.iloc[i].astype(str).str.lower()
            if row.str.contains("year").any() and row.str.contains("s&p 500").any():
                hdr = row.tolist()
                col = lambda key: next(j for j, h in enumerate(hdr) if key in h)
                body = df.iloc[i + 1:]
                out = pd.DataFrame({
                    "year": pd.to_numeric(body.iloc[:, col("year")], errors="coerce"),
                    "sp500": pd.to_numeric(body.iloc[:, col("s&p 500")], errors="coerce"),
                    "tbill_3m": pd.to_numeric(body.iloc[:, col("t.bill")], errors="coerce"),
                    "tbond_10y": pd.to_numeric(body.iloc[:, col("t. bond")], errors="coerce"),
                }).dropna()
                out = out[(out.year >= 1928) & (out.year < 2100)]
                if len(out) > 50:
                    out["year"] = out.year.astype(int)
                    # spreadsheet stores fractions; snapshot stores percent
                    for c in ["sp500", "tbill_3m", "tbond_10y"]:
                        out[c] = (out[c] * 100).round(2)
                    return out.drop_duplicates("year").reset_index(drop=True)
    raise ValueError("Could not locate the annual returns table in histretSP.xls")


def _parse_fred_cpi(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(csv_bytes))
    df.columns = ["date", "cpi"]
    df["date"] = pd.to_datetime(df["date"])
    dec = df[df.date.dt.month == 12].set_index(df.date.dt.year)["cpi"]
    infl = (dec.pct_change() * 100).round(1).dropna()
    return pd.DataFrame({"year": infl.index.astype(int), "cpi_dec_dec": infl.values})


def download(write: bool = True) -> pd.DataFrame:
    """Fetch fresh data from Damodaran and FRED; optionally overwrite the snapshot."""
    rets = _parse_damodaran(_get(DAMODARAN_XLS))
    cpi = _parse_fred_cpi(_get(FRED_CPI_CSV))
    if write:
        RAW.mkdir(parents=True, exist_ok=True)
        rets.to_csv(RAW / "damodaran_returns_downloaded.csv", index=False)
        cpi.to_csv(RAW / "cpi_dec_dec_downloaded.csv", index=False)
    return _combine(rets, cpi)


# ---------------------------------------------------------------- load
def _combine(rets: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    df = rets[["year", "sp500", "tbond_10y", "tbill_3m"]].merge(cpi, on="year", how="inner")
    df = df.set_index("year").sort_index() / 100.0
    df.columns = ["stocks", "bonds", "bills", "inflation"]
    return df


def load(prefer_downloaded: bool = True, intl_series: str = "intl") -> pd.DataFrame:
    """Annual table indexed by year with columns stocks, bonds, bills, inflation and
    (when intl_stocks.csv exists) intl = developed ex-US stocks in USD. All decimals.
    intl_series: "intl" (base) or "intl_stress" (wartime gaps filled with heavy losses)."""
    r_dl, c_dl = RAW / "damodaran_returns_downloaded.csv", RAW / "cpi_dec_dec_downloaded.csv"
    if prefer_downloaded and r_dl.exists() and c_dl.exists():
        df = _combine(pd.read_csv(r_dl), pd.read_csv(c_dl))
    else:
        df = _combine(pd.read_csv(RETURNS_CSV), pd.read_csv(CPI_CSV))
    if INTL_CSV.exists():
        intl = pd.read_csv(INTL_CSV, usecols=["year", intl_series]).set_index("year")[intl_series] / 100
        df["intl"] = intl.reindex(df.index)
    return df


def with_intl(df: pd.DataFrame, share: float) -> pd.DataFrame:
    """Replace `stocks` with a mix: (1-share) US + share international, rebalanced yearly."""
    if share == 0:
        return df
    if "intl" not in df or df["intl"].isna().any():
        raise ValueError("international returns missing; run scripts/build_intl.py")
    return df.assign(stocks=(1 - share) * df["stocks"] + share * df["intl"])
