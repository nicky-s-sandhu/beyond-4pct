# Licence for `intl_stocks.csv`

`intl_stocks.csv` is derived from the Jordà-Schularick-Taylor (JST) Macrohistory Database,
Release 6, and is therefore shared under the same licence:
**[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)**.

- **Non-commercial use only.** You may copy and adapt this file for non-commercial (for example,
  academic or personal) purposes.
- **Share alike.** Anything you derive from it must be shared under CC BY-NC-SA 4.0.
- **Attribution.** Cite the JST database as required by its authors (below).

The MIT licence in the repository root covers the code only, not this file.

## What was derived, and the changes made

- Columns `intl`, `intl_stress`, `intl_gdp`, `intl_equal`, `n_countries`, `largest` for 1928–1969
  are computed from JST equity total returns (`eq_tr`), exchange rates (`xrusd`), real GDP per capita
  (`rgdpmad`) and population (`pop`) for 15 non-US countries, converted to US dollars and weighted
  by prior-year real GDP.
- Changes: Germany 1949 uses the official Deutsche Mark parity (3.33 → 4.20 per USD) instead of
  JST's rate across the 1948 currency reform; `intl_stress` fills wartime gaps with assumed losses.
  See `scripts/build_intl.py`.
- From 1970 the `intl` and `intl_stress` columns use MSCI World ex USA annual returns
  (column `msci_wxus`), not JST data.

## Required citations

Database:

> Òscar Jordà, Moritz Schularick, and Alan M. Taylor. 2017. "Macrofinancial History and the New
> Business Cycle Facts." In *NBER Macroeconomics Annual 2016*, volume 31, edited by Martin
> Eichenbaum and Jonathan A. Parker. Chicago: University of Chicago Press.

Rates of return (the asset-return data used here):

> Òscar Jordà, Katharina Knoll, Dmitry Kuvshinov, Moritz Schularick, and Alan M. Taylor. 2019.
> "The Rate of Return on Everything, 1870–2015." *Quarterly Journal of Economics* 134(3): 1225–1298.

Database consulted: Release 6, October 2026. Source: <https://www.macrohistory.net/database/>
