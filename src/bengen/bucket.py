"""Cash-bucket hedge on top of any spending rule (constant real or guardrails).

Holdings: stocks S, bonds B, cash C (cash earns the T-bill rate).
Targets: `stocks` share, `cash` share (taken out of bonds), bonds = the rest.

Each year (withdrawals at year end, as everywhere else in this project):
  1. Spending is set by the rule (inflation raise, drift, guardrails on the
     total portfolio, floor and cap) -- identical to strategies.fast_guardrails.
  2. Returns are applied; a stock index tracks its running peak.
  3. Downturn = stock index more than `threshold` below its peak.
     In a downturn (for at most `max_down_years` in a row): spending comes
     from cash, then bonds, then (only if both are empty) stocks. No rebalancing,
     so stocks are never sold.
     Otherwise: withdraw, then -- if cash is below target and stocks rose this
     year -- refill cash by target / `refill_years`, then rebalance the
     invested (non-cash) money back to the stock/bond ratio. Because the rest is
     rebalanced, a refill booked against stocks or bonds ends up the same.
  bucket=False holds cash at its target share every year (static mix), which
  isolates cash drag from the timing rule. cash=0, bucket=False reproduces
  strategies.fast_guardrails exactly.
"""
from __future__ import annotations


def run(stock_r, bond_r, bill_r, infl, rate, stocks, cash=0.10, bucket=True, step=0.0, band=0.2,
        floor=None, ceiling=None, drift=0.0, floor_drift=None, threshold=0.10, max_down_years=5,
        refill_years=5):
    """Simulate one retiree. Returns dict with real spending list, depleted flag, final real balance,
    years spent drawing from the bucket, and the cash share path."""
    floor_drift = drift if floor_drift is None else floor_drift
    bonds_w = 1.0 - stocks - cash
    if bonds_w < -1e-12:
        raise ValueError("stocks + cash > 100%")
    inv_stock_share = stocks / (stocks + bonds_w) if stocks + bonds_w > 0 else 1.0
    S, B, C = stocks, max(bonds_w, 0.0), cash
    idx = peak = 1.0
    down_run, bucket_years = 0, 0
    price, spend, reals, depleted = 1.0, rate, [], False
    lo_g, hi_g = rate * (1 + band), rate * (1 - band)
    n = len(stock_r)
    for i in range(n):
        if i > 0:
            bal = S + B + C
            price *= 1 + infl[i - 1]
            spend *= (1 + infl[i - 1]) * (1 + drift)
            if step > 0 and bal > 0:
                wr = spend / bal
                if wr > lo_g:
                    spend *= 1 - step
                elif wr < hi_g:
                    spend *= 1 + step
            if floor is not None:
                spend = max(spend, floor * rate * price * (1 + floor_drift) ** i)
            if ceiling is not None:
                spend = min(spend, ceiling * rate * price * (1 + drift) ** i)
        S *= 1 + stock_r[i]
        B *= 1 + bond_r[i]
        C *= 1 + bill_r[i]
        idx *= 1 + stock_r[i]
        peak = max(peak, idx)
        in_down = bucket and idx < peak * (1 - threshold)
        total = S + B + C
        take = min(spend, total)
        if take < spend - 1e-12:
            depleted = True
        if in_down and down_run < max_down_years:
            down_run += 1
            bucket_years += 1
            x = take
            d = min(x, C); C -= d; x -= d
            d = min(x, B); B -= d; x -= d
            S -= x
        else:
            if not in_down:
                down_run = 0
            total -= take
            target_c = cash * total
            if bucket:
                if C > target_c:
                    C = target_c
                elif stock_r[i] > 0:
                    C = min(target_c, C + target_c / refill_years)
                C = min(C, total)
            else:
                C = target_c
            inv = total - C
            S, B = inv * inv_stock_share, inv * (1 - inv_stock_share)
        reals.append(take / price)
    final = (S + B + C) / (price * (1 + infl[n - 1]))
    return {"reals": reals, "depleted": depleted, "final": final, "bucket_years": bucket_years}
