"""One map of every strategy tried: early spending against the risk of a big drop.

x = typical (median) real spending in years 1-10, $ per $100 of starting portfolio
y = share of the 69 retirees whose real spending ever fell 30%+ below their
    first-year spending, or who ran out of money
Plain measures that mean the same for every plan, so experiments scored with
different objectives can sit on one chart.

    python scripts/experiment_map.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bengen import data, vec  # noqa: E402

OUT = ROOT / "output" / "summary"
INK, MUTED, GRID_C = "#0b0b0b", "#52514e", "#e5e4df"
ACCENT, REJECT, BASE = "#2a78d6", "#bb5228", "#8a8984"


def load(path, key):
    return vec.Params(**json.load(open(ROOT / path))[key])


def experiments():
    prev8 = vec.Params(rate=0.08, stocks=0.8, intl=0.25, band=0.2, cut_step=0.3, raise_step=0.3, floor=0.5,
                       ceiling=2.0, drift=-0.005)
    best = "output/decline/best/chosen_params.json"
    return [
        # label, params, status, why
        ("Bengen 4%", vec.Params(rate=0.04, stocks=0.5), "baseline", "Never cuts; lowest spending"),
        ("Bengen 5%", vec.Params(rate=0.05, stocks=0.5), "rejected", "A quarter of retirees run out"),
        ("Guardrails, no floor", vec.Params(rate=0.05, stocks=0.5, band=0.2, cut_step=0.1, raise_step=0.1),
         "rejected", "Cuts compound; worst retirees near $2"),
        ("Previous 8% plan", prev8, "rejected", "45% of retirees cut to the floor"),
        ("8% plan + cash bucket", vec.Params(**{**prev8.as_dict(), "cash": 0.10, "bucket": True}), "rejected",
         "Barely changes anything"),
        ("Smooth-score ratchet", vec.Params(rate=0.048, stocks=1.0, intl=0.45, band=0.0, raise_step=0.13,
                                            drift=-0.009), "rejected", "Back-loaded; 45% international"),
        ("Smile, big raises", load("output/smile/chosen_params.json", "Smile + tiny adjustments + cash (cuts <=5%)"),
         "rejected", "Most retirees give back raises"),
        ("Smile, tiny both ways", load("output/smile/chosen_params.json",
                                       "Smile + tiny both ways (cuts and raises <=5%)"), "rejected",
         "Lower early spending; deep cuts below plan"),
        ("Mirror smile", load("output/smile/mirror/chosen_params.json", "Mirror smile, cuts <=5%, raises <=10%"),
         "rejected", "Median path flat; late run-outs"),
        ("75% floor, raises ≤5%", load(best, "Cuts <=5%, raises <=5%"), "rejected", "5 retirees run out"),
        ("75% floor, raises ≤10%", load(best, "Cuts <=5%, raises <=10%"), "rejected", "4 retirees run out"),
        ("Recommended: 75% floor, raises ≤15%", load(best, "Cuts <=5%, raises <=15%"), "recommended",
         "1 retiree runs out; no drop below 75%"),
    ]


def measure(df, p):
    out = vec.simulate(p, *vec.windows(df, p.intl)[1:])
    R, ran = out["reals"], out["depleted"]
    drop = (1 - R / R[:, :1]).max(axis=1)
    return {"early": float(np.median(R[:, :10].mean(axis=1))) * 100,
            "big_drop": float(np.mean((drop >= 0.30) | ran)), "ran_out": int(ran.sum()),
            "lifetime": float(np.median(R.mean(axis=1))) * 100}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = data.load()
    df = df.assign(bonds=0.5 * df.bills + 0.5 * df.bonds)
    rows = []
    for lab, p, status, why in experiments():
        rows.append({"experiment": lab, "status": status, "why": why, "start": p.rate, **measure(df, p)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "experiment_map.csv", index=False)

    fig, ax = plt.subplots(figsize=(11, 6.4))
    col = {"baseline": BASE, "rejected": REJECT, "recommended": ACCENT}
    # explicit label positions (data coordinates) with leader lines, so no label sits on the wrong point
    pos = {"Bengen 4%": (4.1, 7), "Bengen 5%": (5.1, 29), "Guardrails, no floor": (5.1, 55),
           "Previous 8% plan": (6.75, 96), "8% plan + cash bucket": (6.45, 78), "Smooth-score ratchet": (5.15, 14),
           "Smile, big raises": (7.15, 64), "Smile, tiny both ways": (5.85, 46), "Mirror smile": (7.05, 28),
           "75% floor, raises ≤5%": (5.55, 24), "75% floor, raises ≤10%": (6.15, 18),
           "Recommended: 75% floor, raises ≤15%": (6.72, 8)}
    for _, r in res.iterrows():
        big = r.status == "recommended"
        ax.scatter(r.early, r.big_drop * 100, s=150 if big else 60, color=col[r.status], zorder=3,
                   edgecolor="white", lw=1.5)
        tx, ty = pos[r.experiment]
        ax.annotate(f"{r.experiment}  ({r.early:.2f}, {r.big_drop:.0%})".replace("$", ""), (r.early, r.big_drop * 100),
                    xytext=(tx, ty), textcoords="data", ha="left", va="center", fontsize=9 if big else 8.3,
                    color=INK, fontweight="bold" if big else "normal",
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7, shrinkA=0, shrinkB=4))
    ax.set_xlabel("Typical spending in years 1–10 (real \\$ per \\$100 of starting portfolio)", color=MUTED,
                  fontsize=9.5)
    ax.set_ylabel("Retirees whose spending ever fell 30%+ below year 1, or ran out (%)", color=MUTED,
                  fontsize=9.5)
    ax.set_ylim(-4, 104)
    ax.set_xlim(3.6, 8.6)
    ax.grid(color=GRID_C, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID_C)
    ax.tick_params(colors=MUTED, labelsize=9)

    ax.text(3.7, 72, "Better = further right (more early spending)\nand lower (fewer big drops)", ha="left", va="top",
            fontsize=8.5, color=MUTED)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker="o", ls="", color=col[k], ms=8, label=l) for k, l in
               (("recommended", "Recommended"), ("rejected", "Tried and rejected"), ("baseline", "Baseline"))]
    ax.legend(handles=handles, frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("Every strategy we tried: the recommended plan spends 64% more than Bengen early on with almost no "
                 "big drops", x=0.01, ha="left", fontsize=12.5, color=INK)
    fig.text(0.01, 0.915, "69 historical 30-year retirements, 1928–1996 starts. A drop is measured against the "
             "retiree's own first-year spending, so planned declines count too.", fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / "experiment_map.png", dpi=150)
    plt.close(fig)
    with pd.option_context("display.width", 200):
        print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
