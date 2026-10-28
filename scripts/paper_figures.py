"""Figures for the journal manuscript (output/paper/)."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "app"))
import alt_charts as ac  # noqa: E402
import plan_summary as ps  # noqa: E402
import model  # noqa: E402

OUT = ROOT / "output" / "paper"
OUT.mkdir(parents=True, exist_ok=True)

ROWS = [  # (label, strategy in final_robust.csv)
    ("Guardrail rule tuned on history (6.1% start, 75% floor)", "Recommended plan"),
    ("Rising equity glidepath, tuned on history", "History-tuned: recommended rule + glidepath"),
    ("CAPE-aware amortization, tuned on history", "History-tuned: CAPE amortization"),
    ("Amortization (no hard floor), tuned on reshuffled history", "Robust: amortization"),
    ("Percent of portfolio with limits, tuned on reshuffled history", "Robust: percent of portfolio with limits"),
    ("Vanguard dynamic spending (published settings)", "Vanguard dynamic, published (5%, +5%/-2.5%)"),
    ("ERN CAPE rule (published settings)", "ERN CAPE rule (1.75% + 0.5/CAPE), 75/25"),
    ("Bengen 4% (50/50)", "Bengen 4% (50/50 US)"),
]


def figure1():
    """Share of retirements that ran out: in the history used for tuning vs in reshuffled history."""
    df = pd.read_csv(ROOT / "output" / "alt" / "final_robust.csv")
    d = df[df.test.isin(["history", "bootstrap"])].pivot(index="strategy", columns="test", values="ran_out_pct")
    c = df[df.test.isin(["history", "bootstrap"])].pivot(index="strategy", columns="test", values="ce")
    data = [(lab, d.loc[k, "history"], d.loc[k, "bootstrap"], c.loc[k, "history"], c.loc[k, "bootstrap"])
            for lab, k in ROWS]
    s = model.RECOMMENDED
    ob, mb = ps.boot(s)
    r = model.run(s)
    data.append(("Robust rule: Blanchett path, 10% cap, 2% target (this paper)", r.m["ran_out"] / 69 * 100,
                 ob["depleted"].mean() * 100, r.m["ce"], mb["ce"]))
    data.sort(key=lambda x: -x[2])
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for i, (lab, h, b, *_ ) in enumerate(data):
        ax.plot([h, b], [i, i], color="#cccccc", lw=2, zorder=1)
        ax.scatter([h], [i], s=55, color="white", edgecolor="black", linewidth=1.3, zorder=2,
                   label="69 historical retirements" if i == 0 else None)
        ax.scatter([b], [i], s=55, color="black", zorder=3, label="5,000 reshuffled retirements" if i == 0 else None)
        ax.text(max(h, b) + 0.4, i, f"{h:.1f}% \u2192 {b:.1f}%", va="center", fontsize=8.5)
    ax.set_yticks(range(len(data)), [x[0] for x in data], fontsize=8.5)
    ax.set_xlabel("Retirements that ran out of money within 30 years (%)")
    ax.set_xlim(-0.5, 27)
    ax.grid(axis="x", color="#e5e5e5", lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "figure1_history_vs_reshuffled.png", dpi=200)
    return data


if __name__ == "__main__":
    for r in figure1():
        print(f"{r[0]:62s} out {r[1]:.1f} -> {r[2]:.1f}   score {r[3]:.2f} -> {r[4]:.2f}")
    import shutil
    shutil.copy(ROOT / "output" / "alt" / "plan_compare.png", OUT / "figure2_spending_paths.png")
