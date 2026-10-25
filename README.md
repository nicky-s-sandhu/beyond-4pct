# Beyond the 4% rule — a historical backtest

Re-runs William P. Bengen, "Determining Withdrawal Rates Using Historical Data"
(*Journal of Financial Planning*, Oct 1994), then tests flexible spending rules, allocation,
front-loading and international diversification on actual returns through 2025.

## Key findings

69 overlapping 30-year retirements starting 1928–1996. Spending in real dollars per $100 of
starting portfolio; "typical" = median retiree.

| Change added | Safe starting rate | Typical spending, yrs 1–10 | Failures (of 69) |
|---|---|---|---|
| Bengen: constant real spending, 50/50 US | 4.0% (max 4.16%, worst start 1966) | $4.00 | 0 |
| Guardrails ±30%, $4 floor, 80% stocks | 5.5% | $5.67 | 0 |
| Real spending −0.5%/yr, floor declines too | 6.3% | $6.29 | 0 |
| 25% of stocks international | 8.0% | $7.42 | 0 |
| Accept 95% success | 9.0% | $8.02 | 3 |

- Guardrails without a floor make things worse; a floor plus large steps is what works.
- About 80% stocks is the sweet spot; at 90%+ the 1929 retiree always fails. Leverage never helps.
- Front-loading helps only if the minimum declines too. A spending ceiling never raises the safe rate.
- 25% international is the biggest single gain and survives stress tests.
- These are in-sample optimums (no fees or taxes); a realistic target is 1–1.5 points lower.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/reproduce.py --download   # fetch fresh data, then run
python scripts/reproduce.py              # or run on the bundled snapshot
pytest
```
Outputs land in `output/`: `results.md`, `safemax_30yr_50_50.csv`, and three charts.

Options: `--timing start|end` (default `end`), `--bonds intermediate|10y` (default `intermediate`).

## Experiments

### Guardrails (`scripts/guardrails.py`)
Guyton-Klinger-style rule: each year spending rises with inflation, then is cut by `step`
if the current withdrawal rate is above `initial × (1 + band)` or raised by `step` if it is
below `initial × (1 − band)`. **`--steps` is the variance knob**: the largest real change in
spending in any single year. `step = 0` is exactly Bengen's rule.

```bash
python scripts/guardrails.py                          # 4% and 5%, steps 0–25%
python scripts/guardrails.py --floor 0.8 --name floor80
python scripts/guardrails.py --rates 0.055 --steps 0,0.1,0.2 --band 0.15 --gk
```
Options: `--band`, `--floor` / `--ceiling` (multiples of year-1 real spending), `--gk`
(skip inflation raise after a losing year; no cuts in the last 15 years), `--stocks`,
`--horizon`, `--focus-year`. Outputs go to `output/guardrails/[name]/`.

### Best-strategy search (`scripts/optimize.py`)
Grid over stock share (60%–125%, above 100% = leverage at T-bills + 1%), guardrail step,
spending ceiling and planned real drift. For each combination it finds the highest starting rate
(0.1% grid) at which the required share of historical retirees succeed. Success = real spending
never below `--target` (default $4 per $100) and never running out. A floor sits at the target.

- `--success 0.95`: required historical success rate (overrides `--allow K`).
- `--drifts 0,-0.005`: planned real spending change per year (−0.005 = inflation − 0.5%).
  By default the floor declines at the same rate; `--flat-floor` keeps it flat.
- `--ceilings 0,1,1.25,1.5,2,3`: cap on spending as a multiple of the planned path (0 = none).
- `--rank early|avg`: rank by median spending in years 1–10 (default) or over all years.

```bash
python scripts/optimize.py --success 0.95 --name p95
python scripts/optimize.py --success 1.0  --name strict
```
Outputs in `output/optimize/[name]/`: `results.md`, `optimize_grid.csv`, heatmaps per drift,
`spending_fan_top_pick.png` and `spending_shape.png` (median vs 5th-percentile retiree).

### International diversification (`--intl`, `scripts/intl_sweep.py`)
`--intl 0.25` (the default in `optimize.py` and `guardrails.py`) puts 25% of the stock allocation in
developed ex-US stocks, rebalanced yearly. `reproduce.py` stays US-only to match Bengen.
`--intl-stress` uses a pessimistic series where wartime data gaps are filled with heavy losses.

```bash
python scripts/intl_sweep.py                       # max safe start vs intl share, fixed strategy
python scripts/optimize.py --success 0.95 --intl 0 --name p95_us
python scripts/optimize.py --success 0.95 --name p95_intl25
python scripts/build_intl.py [JSTdatasetR6.csv]    # rebuild data/raw/intl_stocks.csv
# The raw JST file is not in the repo: download JSTdatasetR6 from https://www.macrohistory.net/database/
# into data/external/ (as CSV). The derived series data/raw/intl_stocks.csv is included.
```

## Data
| Series | Source | Notes |
|---|---|---|
| Stocks | Damodaran, S&P 500 total return (histretSP.xls) | 1928– |
| Bonds | Damodaran, 10-yr US Treasury total return | 1928– |
| Bills | Damodaran, 3-month T-bill | used for the intermediate-bond proxy |
| Inflation | CPI-U NSA, Dec→Dec (FRED `CPIAUCNS`) | |
| International stocks | 1928–69: JST Macrohistory R6, 15 developed countries, USD, real-GDP weighted; 1970–2025: MSCI World ex USA (USD total return) | `data/raw/intl_stocks.csv` |

International notes: JST lacks equity data for Canada and Ireland; Germany 1949 uses the official DM
parity because JST's exchange rate straddles the 1948 currency reform; country-years with missing
data are skipped (the `intl_stress` column fills them with heavy losses instead). JST's Japanese
returns look smoothed after 1970, so MSCI replaces JST from 1970. MSCI World ex USA was checked
against MSCI's official EAFE factsheet for 2012–2025 (within ~2pp a year; the gap is Canada).

`data/raw/*.csv` is a snapshot transcribed from Damodaran's web table and
usinflationcalculator.com's Dec→Dec table. `--download` pulls the original files and
saves `*_downloaded.csv`, which are then preferred — diff them against the snapshot once.

## Method (as in Bengen 1994)
- Portfolio starts at 1.0 on Jan 1 of the retirement year; first withdrawal = rate × 1.0.
- Withdrawals rise each year with CPI (constant real spending).
- Rebalanced annually to a fixed stock/bond mix.
- **Bengen mode:** actual data through 1992, then each series' historical average (Bengen's data ended in 1992).
- Retirees start 1928–1976 (Bengen: 1926–1976; Damodaran's data starts in 1928).

## Known differences from the paper
- Bengen used Ibbotson SBBI large-company stocks and **intermediate-term** government bonds (~5-yr).
  Damodaran only has 10-yr Treasuries, which lost more in 1966–81. The default `intermediate` proxy
  (½ T-bills + ½ 10-yr) approximates a ~5-yr duration and closes most of the gap; use `--bonds 10y` to see the raw effect.
- Bengen's post-1992 averages came from Ibbotson 1926–92; ours are computed from this data (1928–92).
