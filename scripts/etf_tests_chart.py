"""Chart for the four ETF tests (output/etf_tests/comparison.png)."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output" / "etf_tests"
INK, MUTED, GRID, ACCENT, GREY = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#b9b8b2"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
d = pd.read_csv(OUT / "plan_settings.csv").sort_values("1928-2020 rate")
y = np.arange(len(d))
fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(15, 6.2), sharey=True, gridspec_kw={"width_ratios": [1.5, 1, 1]})
col = [GREY if p.startswith("Fixed") else (ACCENT if p.startswith("ECY") else "#86b6ef") for p in d.portfolio]
base = d[d.portfolio.str.startswith("Fixed")].iloc[0]
a1.barh(y, d["1928-2020 rate"], color=col, height=0.6)
a1.scatter(d["1928-74 only rate"], y, marker="v", color=INK, s=28, zorder=3, label="Only years 1928–1974")
a1.scatter(d["1975-2020 only rate"], y, marker="^", color=INK, s=28, facecolors="none", zorder=3, label="Only years 1975–2020")
for yi, v in zip(y, d["1928-2020 rate"]):
    a1.text(4.05, yi, f"{v:.2f}%", va="center", fontsize=8.5, color="white", fontweight="bold")
a1.axvline(base["1928-2020 rate"], color=MUTED, lw=0.8, ls="--")
a1.set_xlim(4, 9); a1.set_yticks(y, d.portfolio)
a1.set_title("Starting rate with 2% running out\n(bar: reshuffled 1928–2020; markers: each half alone)", loc="left", fontsize=10.5, color=INK)
a1.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2); a1.grid(axis="x", color=GRID, lw=0.6)
a2.barh(y, d["ran_out_at_6.5"], color=col, height=0.6)
for yi, v in zip(y, d["ran_out_at_6.5"]):
    a2.text(v + 0.04, yi, f"{v:.1f}%", va="center", fontsize=8.5, color=MUTED)
a2.set_title("Ran out at the plan's 6.5% start", loc="left", fontsize=10.5, color=INK); a2.set_xlim(0, 2.6)
a2.grid(axis="x", color=GRID, lw=0.6)
a3.barh(y, d["1928-2020 ce"], color=col, height=0.6)
for yi, v in zip(y, d["1928-2020 ce"]):
    a3.text(v + 0.03, yi, f"{v:.2f}", va="center", fontsize=8.5, color=MUTED)
a3.set_xlim(4, 6); a3.axvline(base["1928-2020 ce"], color=MUTED, lw=0.8, ls="--")
a3.set_title("Smooth-spending score at the 2% rate\n(dollars per \\$100 saved)", loc="left", fontsize=10.5, color=INK)
a3.grid(axis="x", color=GRID, lw=0.6)
fig.suptitle("Survey tests inside the recommended plan (spending settings unchanged; stocks 70% US / 30% international)",
             x=0.01, ha="left", fontsize=12.5)
fig.tight_layout(); fig.savefig(OUT / "comparison.png", dpi=150)
