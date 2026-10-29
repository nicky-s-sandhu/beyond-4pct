# Following the recommended plan, year by year

A practical guide to running the [recommended withdrawal plan](https://github.com/nicky-s-sandhu/beyond-4pct#recommended-plan) from
*Beyond the 4% rule*. It turns the rule into a short January routine, gives the planned change for every age so no
formula is needed, and walks through two real retirements: one that started badly (2000) and one that started well (1990).

*Educational material based on a historical study, not financial advice. Talk to a qualified adviser before acting on it.*

## The rule in one paragraph

Start by spending 6.5% of your portfolio, with 80% in stocks (30% of those outside the U.S.) and 20% in bonds. Each January
raise last year's spending by inflation and lower it by the planned change for your age (about 1% a year on average). If that
amount is more than 7.93% of your portfolio, cut it by 8.5%; if it is less than 5.07%, raise it by 15%. Never spend more
than 10% above the planned path, and never less than 42% of your first year's spending, adjusted for inflation. Rebalance
once a year.

In the study this plan ran out of money in none of the 69 U.S. retirements since 1928 and in about 2% of 5,000 retirements
reshuffled from that history. The price is that about one retiree in four has a lean stretch after a bad start, like the
2000 example below.

## Setting up (once, at retirement)

Write down four numbers. All examples use a $1,000,000 portfolio.

| Number | How to work it out | $1M example |
|---|---|---|
| **Starting portfolio** | Value of the invested savings this plan covers | $1,000,000 |
| **First-year spending** | 6.5% of the starting portfolio | $65,000 |
| **Floor** | 42% of first-year spending | $27,300 |
| **Planned amount** | Starts equal to first-year spending | $65,000 |

The two trigger levels never change: **7.93%** (6.5% × 1.22) and **5.07%** (6.5% × 0.78).

**Investments.** 80% stocks and 20% bonds. Within stocks, 70% U.S. and 30% developed markets outside the U.S., so
56% U.S. stocks, 24% international stocks and 20% bonds overall. The study's bonds were half 3-month Treasury bills and half
10-year Treasuries; an intermediate-term Treasury fund is a close substitute. Low-cost index funds matter: in the study a
0.25% yearly fee raised the chance of running out from about 2% to about 3%.

## Every January

| Step | What to do | Formula |
|---|---|---|
| 1 | Look up last year's inflation | U.S. CPI-U, December to December (published by the Bureau of Labor Statistics in mid-January) |
| 2 | Look up this year's planned change for your age | Table below |
| 3 | Update the floor | floor × (1 + inflation) |
| 4 | Update the planned amount and the cap | planned × (1 + inflation) × (1 + planned change); cap = 1.10 × planned |
| 5 | Work out provisional spending | last year's actual spending × (1 + inflation) × (1 + planned change) |
| 6 | Work out the withdrawal rate | provisional spending ÷ portfolio value today |
| 7 | Adjust | above 7.93%: × 0.915 (cut 8.5%). Below 5.07%: × 1.15 (raise 15%). Otherwise keep it |
| 8 | Apply the cap, then the floor | no more than the cap; no less than the floor |
| 9 | Rebalance and set aside the year's spending | back to 56% U.S. stocks, 24% international, 20% bonds |

The result of step 8 is this year's spending. Next January, step 5 starts from it.

**A spreadsheet version** (one row per year; columns as named):

```
inflation        = last year's CPI-U change
change           = planned change for this age (table below)
floor            = previous floor × (1 + inflation)
planned          = previous planned × (1 + inflation) × (1 + change)
provisional      = previous spending × (1 + inflation) × (1 + change)
rate             = provisional / portfolio
adjusted         = IF(rate > 7.93%, provisional × 0.915, IF(rate < 5.07%, provisional × 1.15, provisional))
spending         = MAX(floor, MIN(1.10 × planned, adjusted))
```

## Planned change by age

These come from David Blanchett's research on how retirees actually spend ("Exploring the Retirement Consumption
Puzzle", *Journal of Financial Planning*, 2014), for a household spending about $75,000 a year. Use the line for your
age as you move into the new year: a 70-year-old turning 71 uses −1.1%.

| Age | Planned change | Age | Planned change | Age | Planned change |
|---|---|---|---|---|---|
| 65 → 66 | −0.3% | 75 → 76 | −1.6% | 85 → 86 | −1.3% |
| 66 → 67 | −0.5% | 76 → 77 | −1.6% | 86 → 87 | −1.2% |
| 67 → 68 | −0.7% | 77 → 78 | −1.6% | 87 → 88 | −1.0% |
| 68 → 69 | −0.8% | 78 → 79 | −1.6% | 88 → 89 | −0.9% |
| 69 → 70 | −1.0% | 79 → 80 | −1.6% | 89 → 90 | −0.7% |
| 70 → 71 | −1.1% | 80 → 81 | −1.6% | 90 → 91 | −0.5% |
| 71 → 72 | −1.2% | 81 → 82 | −1.6% | 91 → 92 | −0.3% |
| 72 → 73 | −1.3% | 82 → 83 | −1.5% | 92 → 93 | −0.1% |
| 73 → 74 | −1.4% | 83 → 84 | −1.5% | 93 → 94 | +0.1% |
| 74 → 75 | −1.5% | 84 → 85 | −1.4% | 94 → 95 | +0.4% |

Over 30 years these add up to planned spending about 27% lower after inflation, gentlest at the start and end of
retirement. For a household spending about $50,000 a year each step is roughly 0.3 points smaller (21% over 30 years);
at $100,000, roughly 0.2 points larger (31%).

## Worked example 1: a bad start (retiring in January 2000)

A 65-year-old retires with $1,000,000 just before the dot-com crash, then meets the 2008 crisis. Actual returns and inflation;
withdrawals made at the end of each year as in the study.

| Year | Age | Last year's inflation | Planned change | Portfolio, Jan 1 | Withdrawal rate | Action | Spending | Spending in 2000 dollars |
|---|---|---|---|---|---|---|---|---|
| 2000 | 65 |  |  | $1,000,000 | 6.5% | first year | $65,000 | $65,000 |
| 2001 | 66 | 3.4% | -0.3% | $875,412 | 7.7% | no change | $67,029 | $64,825 |
| 2002 | 67 | 1.6% | -0.5% | $713,673 | 9.5% | cut 8.5% | $62,018 | $59,035 |
| 2003 | 68 | 2.4% | -0.7% | $549,262 | 11.5% | cut 8.5% | $57,727 | $53,661 |
| 2004 | 69 | 1.9% | -0.8% | $632,271 | 9.2% | cut 8.5% | $53,378 | $48,694 |
| 2005 | 70 | 3.3% | -1.0% | $652,207 | 8.4% | cut 8.5% | $49,957 | $44,117 |
| 2006 | 71 | 3.4% | -1.1% | $647,343 | 7.9% | no change | $51,077 | $43,623 |
| 2007 | 72 | 2.5% | -1.2% | $697,967 | 7.4% | no change | $51,704 | $43,081 |
| 2008 | 73 | 4.1% | -1.3% | $699,545 | 7.6% | no change | $53,098 | $42,501 |
| 2009 | 74 | 0.1% | -1.4% | $445,775 | 11.8% | cut 8.5% | $47,934 | $38,329 |
| 2010 | 75 | 2.7% | -1.5% | $494,509 | 9.8% | cut 8.5% | $44,363 | $34,541 |
| 2011 | 76 | 1.5% | -1.6% | $506,596 | 8.7% | cut 8.5% | $40,554 | $31,109 |
| 2012 | 77 | 3.0% | -1.6% | $465,803 | 8.8% | cut 8.5% | $37,604 | $28,006 |
| 2013 | 78 | 1.7% | -1.6% | $490,078 | 7.7% | no change | $37,617 | $27,547 |
| 2014 | 79 | 1.5% | -1.6% | $561,670 | 6.7% | no change, held to floor | $37,839 | $27,300 |
| 2015 | 80 | 0.8% | -1.6% | $567,154 | 6.6% | no change, held to floor | $38,142 | $27,300 |

What happened:

- **2002–2005:** the portfolio fell from $1,000,000 to $549,000. The withdrawal rate went above 7.93% four years running, so
  spending was cut 8.5% each time, from $67,000 to about $50,000.
- **2009–2012:** the 2008 crash pushed the rate above 7.93% again; four more cuts brought spending to about $37,600
  (about $28,000 in 2000 dollars).
- **From 2014:** spending reached the floor, $27,300 in 2000 dollars ($37,839 in 2014 dollars), and stayed there through
  2025 because the portfolio never recovered enough to trigger a raise.
- **Result:** the money lasted. After 26 years the portfolio still held $754,000 (about $391,000 in 2000 dollars), but the
  retiree spent the second half of retirement at the floor. This is the plan's trade-off: deep but survivable cuts in the
  worst sequences instead of running out.

## Worked example 2: a good start (retiring in January 1990)

| Year | Age | Last year's inflation | Planned change | Portfolio, Jan 1 | Withdrawal rate | Action | Spending | Spending in 1990 dollars |
|---|---|---|---|---|---|---|---|---|
| 1990 | 65 |  |  | $1,000,000 | 6.5% | first year | $65,000 | $65,000 |
| 1991 | 66 | 6.1% | -0.3% | $877,134 | 7.8% | no change | $68,779 | $64,825 |
| 1992 | 67 | 3.1% | -0.5% | $1,000,963 | 7.1% | no change | $70,576 | $64,519 |
| 1993 | 68 | 2.9% | -0.7% | $956,666 | 7.5% | no change | $72,145 | $64,094 |
| 1994 | 69 | 2.7% | -0.8% | $1,029,314 | 7.1% | no change | $73,480 | $63,564 |
| 1995 | 70 | 2.7% | -1.0% | $978,498 | 7.6% | no change | $74,723 | $62,939 |
| 1996 | 71 | 2.5% | -1.1% | $1,163,840 | 6.5% | no change | $75,733 | $62,235 |
| 1997 | 72 | 3.3% | -1.2% | $1,263,693 | 6.1% | no change | $77,261 | $61,462 |
| 1998 | 73 | 1.7% | -1.3% | $1,447,688 | 5.4% | no change | $77,515 | $60,633 |
| 1999 | 74 | 1.6% | -1.4% | $1,694,996 | 4.6% | raise 15%, held to cap | $85,385 | $65,738 |
| 2000 | 75 | 2.7% | -1.5% | $1,917,141 | 4.5% | raise 15%, held to cap | $86,365 | $64,744 |
| 2001 | 76 | 3.4% | -1.6% | $1,716,538 | 5.1% | no change | $87,899 | $63,727 |
| 2008 | 83 | 4.1% | -1.5% | $1,590,021 | 6.0% | no change | $94,800 | $56,883 |
| 2009 | 84 | 0.1% | -1.5% | $1,039,108 | 9.0% | cut 8.5% | $85,563 | $51,290 |
| 2010 | 85 | 2.7% | -1.4% | $1,178,879 | 7.4% | no change | $86,668 | $50,586 |

*(1990–2001 and 2008–2010 shown.)*

What happened:

- **1990s:** strong markets pushed the withdrawal rate down, but spending simply followed the planned path because the rate
  stayed above 5.07% until 1999.
- **1999 and 2000:** the rate fell below 5.07%, so spending was raised 15%, but the raise was held to the cap of 10% above
  the planned path. That is the cap at work: good years lift spending a little, and the rest stays invested.
- **2009:** the financial crisis pushed the rate to 9.0%, triggering one 8.5% cut; no further cuts were needed.
- **Result:** spending followed the declining pattern from $65,000 to about $48,000 in 1990 dollars by age 94, and the
  portfolio ended 2019 at $1.52 million (about $745,000 in 1990 dollars), a large reserve for late-life care or heirs.

## Common questions

**I am not 65.** Use the table at your actual age. The study simulated 30-year retirements starting at 65; a younger retiree
faces a longer horizon, so starting a little below 6.5% is prudent. The [dashboard](dashboard/) lets you see how the start rate
changes the risk.

**Which inflation figure?** The study used the December-to-December change in the U.S. CPI-U. The figure the Social Security
cost-of-living adjustment is based on is close enough if that is easier to find.

**When exactly do I withdraw?** The study withdrew each year's spending at the end of the year. Withdrawing monthly through
the year makes little difference; what matters is checking the rule once a year, every January.

**I have Social Security or a pension.** The rule covers spending from the portfolio only. Add your other income on top. A
guaranteed income also makes the portfolio's lean years easier to live with, because the floor plus that income is your
true minimum. The study did not include other income, so its risk figures are for the portfolio alone.

**Taxes.** The amounts are before tax. Withdrawals from tax-deferred accounts are taxed as income, so plan your take-home
spending accordingly.

**What if I need extra money one year?** Take it, but count it: the extra withdrawal lowers the portfolio, and the next
January check responds automatically. Frequent extra withdrawals raise the chance of running out.

**What if I am at the floor for years?** That happens after the worst sequences (example 1). The plan was designed to survive
them, but if the floor itself feels too low, the best protection is guaranteed income outside the portfolio, such as
delaying Social Security or buying an annuity, rather than raising the floor, which the study found is the most common way
to make a plan run out.

**What is the money left at the end for?** In most histories the portfolio ends well above zero, because the cap keeps
good-year money invested. It is a reserve for living past 95, for long-term care, or for heirs.

**Can I change the settings?** Yes, but test the change first. The [withdrawal plan explorer](dashboard/) shows how any
change affects spending and the chance of running out.

## Where these numbers come from

The rule's settings come from tuning on 2,000 retirements reshuffled from 1928–2025 history, with at most 2% allowed to run
out; see [Testing beyond history](https://github.com/nicky-s-sandhu/beyond-4pct#testing-beyond-history-why-the-plan-changed). The worked examples follow the
same calculations as the study's engine and are checked against it by `scripts/plan_guide_numbers.py`.
