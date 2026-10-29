"""Valuation-based stock share judged against CAPE's own 10-year average, sliding between a minimum and a maximum.

Rule: rel = CAPE / average of the last 10 January CAPEs (current one included). Stock share is s_mid at rel = 1,
slides linearly down to s_min as rel rises to 1 + width, and up to s_max as rel falls to 1 - width (see
valuation.ramp_shares). All four settings are optimised. Same conventions and objective as valuation_optimize.py
(SAFEMAX: best worst-case fixed real withdrawal, start-of-year withdrawals, annual rebalancing, Shiller data);
retirements start 1890-1993 because the 10-year average needs CAPE from 1881.

Compared with: fixed 60%, the best single stock share, Pfau-Kitces 60/45/30 against CAPE's median to date, and the
earlier optimised three-level rule against the median to date. Out-of-sample: split by time both ways and
walk-forward (each start uses settings chosen only from retirements finished before it).

    python scripts/valuation_rolling.py
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import valuation as V  # noqa: E402

OUT = ROOT / "output" / "valuation"
D = V.load()
LAST = int(D.index.max()) - 29
STARTS = np.arange(1890, LAST + 1)
G = np.round(np.arange(0, 1.0001, 0.05), 2)
WIDTHS = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
CAPE_NOW = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]


class Data:
    def __init__(self, safe):
        take = lambda col: np.array([D[col].loc[y:y + 29].values for y in STARTS])
        self.S, self.B = take("real_stocks"), take(f"real_{safe}")
        self.rel_med, self.rel10 = take("cape_rel"), take("cape_rel10")

    def sub(self, starts):
        k = np.isin(STARTS, starts)
        return self.S[k], self.B[k], self.rel_med[k], self.rel10[k]


def outcomes(w, S, B):
    R = w * S + (1 - w) * B
    sm = V.safemax(R)
    return sm, V.terminal_wealth(R)


# ---- rules: each returns stock shares (n, 30) from params and the valuation arrays
def static(p, rm, r10): return np.full_like(rm, p["s"])
def kp(p, rm, r10): return np.where(rm < 2 / 3, 0.60, np.where(rm > 4 / 3, 0.30, 0.45))
def three(p, rm, r10): return np.where(rm < 2 / 3, p["u"], np.where(rm > 4 / 3, p["o"], p["f"]))
def ramp(p, rm, r10): return V.ramp_shares(r10, p["s_min"], p["s_max"], p["s_mid"], p["width"])


def fit(rule, S, B, rm, r10):
    """Best params by SAFEMAX (ties: higher median MWR)."""
    if rule is kp:
        return {}
    if rule is static:
        grid = [{"s": s} for s in G]
    elif rule is three:
        grid = [{"u": u, "f": f, "o": o} for u, f, o in itertools.product(G, G, G)]
    else:
        grid = [{"s_min": a, "s_max": b, "s_mid": m, "width": wd}
                for a, b in itertools.combinations_with_replacement(G, 2) for m in G if a <= m <= b for wd in WIDTHS]
    best, bp = (-1, -1), None
    for p in grid:
        sm = V.safemax(rule(p, rm, r10) * S + (1 - rule(p, rm, r10)) * B)
        key = (round(sm.min(), 6), np.median(sm))
        if key > best:
            best, bp = key, p
    return bp


def describe(rule, p, win=10):
    if rule is static: return f"{p['s']:.0%} stocks"
    if rule is kp: return "60% cheap / 45% fair / 30% expensive (vs median to date)"
    if rule is three: return f"{p['u']:.0%} cheap / {p['f']:.0%} fair / {p['o']:.0%} expensive (vs median to date)"
    return (f"{p['s_max']:.0%} max ← {p['s_mid']:.0%} at normal → {p['s_min']:.0%} min, "
            f"full swing at ±{p['width']:.0%} from the {win}-year average")


RULES = {"Fixed 60%": None, "Best single stock share": static, "Pfau-Kitces 60/45/30": kp,
         "Optimised 3 levels vs median to date": three, "Sliding vs 10-year average (new)": ramp}


def summarise(name, w, S, B, starts):
    sm, tw = outcomes(w, S, B)
    late = starts >= 1980
    yrs = starts[:, None] + np.arange(30)
    return {"rule": name, "SAFEMAX %": sm.min() * 100, "worst start": int(starts[np.argmin(sm)]),
            "median MWR %": np.median(sm) * 100, "median wealth at 4%": np.median(tw), "avg stocks %": w.mean() * 100,
            "avg stocks since 1995 %": w[yrs >= 1995].mean() * 100 if (yrs >= 1995).any() else np.nan,
            "median MWR, 1980-93 starts %": np.median(sm[late]) * 100}


def shares(rule, p, rm, r10):
    return np.full_like(rm, 0.6) if rule is None else rule(p, rm, r10)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ins, oos, params = [], [], {}
    for safe in ("bills", "bonds"):
        d = Data(safe)
        for name, rule in RULES.items():
            p = {} if rule in (None, kp) else fit(rule, d.S, d.B, d.rel_med, d.rel10)
            params[f"{safe}|{name}"] = {k: float(v) for k, v in p.items()}
            ins.append({"safe": safe, "settings": describe(rule, p) if rule else "60% stocks",
                        **summarise(name, shares(rule, p, d.rel_med, d.rel10), d.S, d.B, STARTS)})
        # out of sample: two splits and walk-forward
        tests = {"fit 1890-1941, test 1942-1993": (range(1890, 1942), range(1942, LAST + 1)),
                 "fit 1942-1993, test 1890-1941": (range(1942, LAST + 1), range(1890, 1942))}
        for label, (tr, te) in tests.items():
            Str, Btr, Mtr, Rtr = d.sub(list(tr)); Ste, Bte, Mte, Rte = d.sub(list(te))
            for name, rule in RULES.items():
                p = {} if rule in (None, kp) else fit(rule, Str, Btr, Mtr, Rtr)
                sm, _ = outcomes(shares(rule, p, Mte, Rte), Ste, Bte)
                oos.append({"safe": safe, "test": label, "rule": name, "test SAFEMAX %": sm.min() * 100,
                            "test median MWR %": np.median(sm) * 100, "settings": describe(rule, p) if rule else "60%"})
        test_years = list(range(1950, LAST + 1))
        for name, rule in RULES.items():
            rates, cache = [], {}
            for y in test_years:
                train = [s for s in STARTS if s <= y - 30]
                if rule in (None, kp):
                    p = {}
                else:
                    if len(train) not in cache:
                        Str, Btr, Mtr, Rtr = d.sub(train)
                        cache[len(train)] = fit(rule, Str, Btr, Mtr, Rtr)
                    p = cache[len(train)]
                Ste, Bte, Mte, Rte = d.sub([y])
                rates.append(outcomes(shares(rule, p, Mte, Rte), Ste, Bte)[0][0])
            rates = np.array(rates)
            oos.append({"safe": safe, "test": "walk-forward, starts 1950-1993", "rule": name,
                        "test SAFEMAX %": rates.min() * 100, "test median MWR %": np.median(rates) * 100,
                        "settings": "re-fit each year" if rule not in (None, kp) else ""})
        print(safe, "done", flush=True)
    a, b = pd.DataFrame(ins), pd.DataFrame(oos)
    a.to_csv(OUT / "rolling_in_sample.csv", index=False); b.to_csv(OUT / "rolling_out_of_sample.csv", index=False)
    (OUT / "rolling_params.json").write_text(json.dumps(params, indent=1))
    with pd.option_context("display.width", 250, "display.max_colwidth", 95, "display.precision", 2):
        print(f"\nIn sample, retirements starting 1890-{LAST}")
        print(a.to_string(index=False))
        print("\nOut of sample")
        print(b.pivot_table(index=["safe", "rule"], columns="test", values="test SAFEMAX %").round(2).to_string())
        print("\nOut of sample, median MWR %")
        print(b.pivot_table(index=["safe", "rule"], columns="test", values="test median MWR %").round(2).to_string())
    now = CAPE_NOW.loc[2026] / CAPE_NOW.loc[2017:2026].mean()
    for safe in ("bills", "bonds"):
        p = params[f"{safe}|Sliding vs 10-year average (new)"]
        print(f"Jan 2026: CAPE {CAPE_NOW.loc[2026]:.1f} is {now:.2f}x its 10-year average -> {safe} rule holds "
              f"{float(V.ramp_shares(np.array([now]), **p)[0]):.0%} stocks")


if __name__ == "__main__":
    main()


def window_sensitivity(windows=(10, 20, 30), first=1910):
    """Same sliding rule with 'normal' = 10-, 20- or 30-year average CAPE, on common starts (first-1993)."""
    starts = np.arange(first, LAST + 1)
    rows = []
    for safe in ("bills", "bonds"):
        take = lambda col: np.array([D[col].loc[y:y + 29].values for y in starts])
        S, B = take("real_stocks"), take(f"real_{safe}")
        f60 = V.safemax(0.6 * S + 0.4 * B)
        for win in windows:
            rel = D["cape_jan"] / D["cape_jan"].rolling(win).mean()
            r = np.array([rel.loc[y:y + 29].values for y in starts])
            p = fit(ramp, S, B, r, r)
            sm = V.safemax(ramp(p, r, r) * S + (1 - ramp(p, r, r)) * B)
            wf, cache = [], {}
            for y in range(first + 40, LAST + 1):
                k = starts <= y - 30
                if k.sum() not in cache:
                    cache[k.sum()] = fit(ramp, S[k], B[k], r[k], r[k])
                q = cache[k.sum()]
                i = list(starts).index(y)
                w = ramp(q, r[i:i + 1], r[i:i + 1])
                wf.append(V.safemax(w * S[i:i + 1] + (1 - w) * B[i:i + 1])[0])
            k = starts >= first + 40
            now = CAPE_NOW.loc[2026] / CAPE_NOW.loc[2026 - win + 1:2026].mean()
            rows.append({"safe": safe, "normal = average of": f"{win} years", "settings": describe(ramp, p, win),
                         "in-sample SAFEMAX %": sm.min() * 100, "walk-forward SAFEMAX %": np.min(wf) * 100,
                         f"fixed 60% same starts %": f60[k].min() * 100,
                         "Jan 2026 CAPE vs normal": now, "Jan 2026 stocks %": float(ramp(p, None, np.array([now]))[0]) * 100})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "rolling_window_sensitivity.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_colwidth", 95, "display.precision", 2):
        print(f"\nWindow sensitivity: in sample starts {first}-{LAST}, walk-forward starts {first + 40}-{LAST}")
        print(df.to_string(index=False))
