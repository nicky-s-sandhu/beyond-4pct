"""Charts for the best-stock-rule search (output/valuation/best_*.png)."""
import sys
from dataclasses import replace
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]
from bengen import data, stockrule as sr  # noqa: E402
import valuation_best as vb  # noqa: E402

OUT = ROOT / "output" / "valuation"
INK, MUTED, GRID, ACCENT, LIGHT, GHOST, WARM = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#86b6ef", "#b9b8b2", "#c0703a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
RULES = [("Fixed 80% (plan)", "Fixed 80%\n(the plan)", GHOST), ("CAPE best (70%, +1/-0.5, 50-100%)", "Best CAPE rule\n50–100%", WARM),
         ("ECY 80%, +1/-1, 50-100%", "ECY rule\n50–100%", ACCENT), ("ECY 80%, +1/-1.5, 0-100%", "ECY rule\n0–100%", LIGHT)]
SETS = [("1928-2025", "Reshuffled\n1928–2025"), ("1881-2022", "Reshuffled\n1881–2022"),
        ("1928-1976 only", "Only years\n1928–1976"), ("1977-2025 only", "Only years\n1977–2025")]


def robust():
    d = pd.read_csv(OUT / "best_robust.csv").set_index("rule")
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    for ax, col, title in ((axes[0], "rate", "Starting rate with 2% running out"), (axes[1], "ce", "Smooth-spending score at that rate")):
        x = np.arange(len(SETS)); w = 0.2
        for k, (r, lab, c) in enumerate(RULES):
            v = [d.loc[r, f"{s} {col}"] for s, _ in SETS]
            ax.bar(x + (k - 1.5) * w, v, w * 0.92, color=c, label=lab.replace("\n", " "))
            for xi, vi in zip(x, v):
                ax.text(xi + (k - 1.5) * w, vi + 0.04, f"{vi:.1f}", ha="center", fontsize=7, color=MUTED)
        ax.set_xticks(x, [s for _, s in SETS], fontsize=8.5); ax.set_ylim(4 if col == "rate" else 3.5, 8.6 if col == "rate" else 6.3)
        ax.set_title(title, loc="left", fontsize=11, color=INK); ax.grid(axis="y", color=GRID, lw=0.8)
    axes[0].set_ylabel("% of starting portfolio"); axes[1].set_ylabel(r"\$ per \$100 saved")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    fig.suptitle("Stock rules inside the recommended plan, on four sets of reshuffled history", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "best_robust.png", dpi=150); plt.close(fig)


def timeline():
    s = sr.signals(data.load(intl_series="intl")["inflation"]).loc[1928:2026]
    med = sr.signals(data.load(intl_series="intl")["inflation"])["ecy"].expanding(min_periods=10).median().loc[1928:2026]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 6.4), sharex=True, gridspec_kw={"height_ratios": [1, 1.2]})
    a1.plot(s.index, s.ecy * 100, color=INK, lw=1.6, label="Excess CAPE yield (ECY)")
    a1.plot(med.index, med * 100, color=MUTED, lw=1, ls="--", label="Its median to date")
    a1.axhline(0, color=GRID, lw=0.8); a1.set_ylabel("%"); a1.set_ylim(-3, 14)
    a1.set_title("ECY = 1/CAPE − (10-year Treasury yield − past 10 years' inflation)", loc="left", fontsize=10.5, color=INK)
    a1.legend(frameon=False, fontsize=8.5, loc="upper right"); a1.grid(axis="y", color=GRID, lw=0.6)
    for name, rule, c, lw in (("Fixed 80% (the plan)", sr.Rule("none", 0.8), GHOST, 2),
                              ("Best CAPE rule, 50–100%", sr.Rule("cape", 0.7, 1, 0.5, 0.5), WARM, 1.4),
                              ("ECY rule, 50–100%", sr.Rule("ecy", 0.8, 1, 1, 0.5), ACCENT, 2.2)):
        a2.step(s.index, sr.shares(rule, s[f"x_{rule.signal}"].fillna(0).values[None, :])[0] * 100, where="post",
                color=c, lw=lw, label=name)
    a2.set_ylim(40, 104); a2.set_ylabel("Stocks (%)"); a2.grid(axis="y", color=GRID, lw=0.6)
    a2.legend(frameon=False, fontsize=8.5, loc="lower left", ncol=3)
    a2.set_title("Stock share each January", loc="left", fontsize=10.5, color=INK)
    fig.tight_layout(); fig.savefig(OUT / "best_timeline.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    robust(); timeline()
    full = vb.Set.boot(vb.frame("plan"))
    for r in (sr.Rule("none", 0.8), sr.Rule("ecy", 0.8, 1, 1, 0.5)):
        W = sr.shares(r, full.X[r.signal])
        o = sr.simulate(replace(vb.P, rate=0.065), W, full.S, full.B, full.I)
        print(r.label(), "run-out at 6.5%:", round(o["depleted"].mean() * 100, 2), "%", "score",
              round(vb.score(r, full, rate=0.065)["ce"], 2))
