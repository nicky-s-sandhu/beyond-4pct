"""Stress tests for the strategies found by alt_optimize.py: fees, out-of-history sequences, other settings.

  - fees: 0.25% and 0.5% a year taken from every asset's return
  - block bootstrap: 5,000 synthetic 30-year retirements stitched from random runs of real history
    (blocks of 10 years on average, all assets, inflation and CAPE moving together)
  - other settings: risk aversion 2 and 5, single person, pessimistic international data, 10-year bonds

    python scripts/alt_robust.py main      # reads output/alt/main.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import alt, data, vec  # noqa: E402
import alt_optimize as ao  # noqa: E402

OUT = ROOT / "output" / "alt"


def to_alt(p):
    names = {f.name for f in fields(alt.Alt)}
    return alt.Alt(**{k: v for k, v in p.items() if k in names})


def bootstrap(n=5000, T=30, block=10, seed=7):
    """Stationary block bootstrap over 1928-2025 (wrapping around), joint across all series."""
    df = data.load(intl_series="intl")
    df = df.assign(bonds=0.5 * df["bills"] + 0.5 * df["bonds"])
    cape = pd.read_csv(ROOT / "data" / "raw" / "shiller_cape_jan.csv").set_index("year")["cape_jan"]
    yrs = df.index.values
    arr = {k: df[k].values for k in ("stocks", "intl", "bonds", "inflation")}
    arr["cape"] = cape.reindex(yrs).values
    idx = alt.bootstrap_index(len(yrs), n, T, block, seed)
    D = ao.Data.__new__(ao.Data)
    D.starts = list(range(n))
    D.US, D.INTL, D.B, D.I, D.K = (arr[k][idx] for k in ("stocks", "intl", "bonds", "inflation", "cape"))
    D.w = vec.survival_weights(T, who="couple")
    return D


def with_fee(D, fee):
    E = ao.Data.__new__(ao.Data)
    E.__dict__.update(D.__dict__)
    E.US, E.INTL, E.B = D.US - fee, D.INTL - fee, D.B - fee
    return E


def summary(m, n):
    return {"ce": m["ce"], "ran_out_pct": m["ran_out"] / n * 100, "below4_pct": float(np.mean(m["low"] < 3.9)) * 100,
            "p5_low": m["p5_low"], "giveback15": m["giveback15"] * 100, "median_final": m["median_final"]}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "main"
    rows = json.loads((OUT / f"{name}.json").read_text())
    D = ao.Data()
    Bs = bootstrap()
    variants = {
        "history": D, "fee 0.25%": with_fee(D, 0.0025), "fee 0.5%": with_fee(D, 0.005),
        "bootstrap": Bs, "bootstrap + fee 0.25%": with_fee(Bs, 0.0025),
        "pessimistic intl": ao.Data(intl_series="intl_stress"), "10-year bonds": ao.Data(bonds="10y"),
    }
    res = []
    for r in rows:
        a = to_alt(r["params"])
        for vname, V in variants.items():
            _, m = V.run(a)
            res.append({"strategy": r["strategy"], "test": vname, **summary(m, len(V.starts))})
        # other scoring choices on history
        for g in (2.0, 5.0):
            out, _ = D.run(a)
            m = alt.metrics(out, tilt=a.drift if a.kind == "guard" else a.tilt, gamma=g, weights=D.w)
            res.append({"strategy": r["strategy"], "test": f"risk aversion {g:g}", **summary(m, len(D.starts))})
    df = pd.DataFrame(res)
    df.to_csv(OUT / f"{name}_robust.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_rows", 500, "display.precision", 2):
        print(df.pivot(index="strategy", columns="test", values="ce").round(2))
        print(df.pivot(index="strategy", columns="test", values="ran_out_pct").round(1))
        print(df.pivot(index="strategy", columns="test", values="below4_pct").round(1))


if __name__ == "__main__":
    main()
