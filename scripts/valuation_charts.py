"""Charts for the valuation-rule reproduction and optimisation (output/valuation/*.png)."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from bengen import valuation as V  # noqa: E402
import repro_pfau_kitces as rpk  # noqa: E402

OUT = ROOT / "output" / "valuation"
INK, MUTED, GRID, ACCENT, BAD, GHOST = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#7f2f14", "#8a8984"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})


def reproduction():
    df, _ = rpk.run()
    items = [(f"{n.replace(' (15 yrs)', '').replace(' (30 yrs)', '')}\n{'stocks + ' + s}, {c.lower() if c != 'All' else 'all starts'}",
              pub, df[(df.strategy == n) & (df.safe == s)][c].iloc[0]) for (n, s, c), pub in rpk.PUBLISHED.items()]
    d = V.load()
    S, B, _ = V.windows(d, list(range(1871, 1981)), safe="bonds")
    items.append(("Pfau (2011): fixed 60/40\nstocks + bonds, worst start (1966)", 3.53, V.safemax(0.6 * S + 0.4 * B).min() * 100))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, (lab, pub, ours) in enumerate(items):
        ax.plot([pub, ours], [i, i], color=GRID, lw=2, zorder=1)
        ax.scatter(pub, i, s=60, facecolor="white", edgecolor=INK, lw=1.4, zorder=2, label="Published" if i == 0 else None)
        ax.scatter(ours, i, s=60, color=ACCENT, zorder=3, label="This reproduction" if i == 0 else None)
        ax.text(max(pub, ours) + 0.06, i, f"{pub:.2f}% vs {ours:.2f}%", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(items)), [x[0] for x in items], fontsize=8.5)
    ax.set_xlim(3.3, 6.6); ax.invert_yaxis()
    ax.set_xlabel("Highest safe withdrawal rate (SAFEMAX, %)")
    ax.grid(axis="x", color=GRID, lw=0.8); ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_title("Reproducing Pfau and Kitces (2015) and Pfau (2011) with Shiller's data", loc="left", fontsize=12, color=INK)
    fig.tight_layout(); fig.savefig(OUT / "reproduction.png", dpi=150)


def optimisation():
    a = pd.read_csv(OUT / "optimised_in_sample.csv"); b = pd.read_csv(OUT / "optimised_out_of_sample.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, safe in zip(axes, ("bills", "bonds")):
        ai = a[a.safe == safe].set_index("rule")["SAFEMAX %"]
        wf = b[(b.safe == safe) & (b.train == "walk-forward")].iloc[0]
        labels = ["Fixed 60%", "Static share,\nbest fit", "Pfau-Kitces\n60/45/30", "Optimised\nvaluation shares"]
        ins = [None, ai["Best static stock share"], ai["Pfau-Kitces 30/45/60"], ai["Optimised shares, 2/3 and 4/3 thresholds"]]
        oos = [wf["fixed 60% test SAFEMAX %"], wf["static fitted, test SAFEMAX %"], wf["Pfau-Kitces 30/45/60 test %"],
               wf["its test SAFEMAX %"]]
        x = np.arange(4)
        ax.bar(x - 0.19, [v if v is not None else 0 for v in ins], 0.36, color=GHOST, label="In sample, starts 1881–1993")
        ax.bar(x + 0.19, oos, 0.36, color=ACCENT, label="Walk-forward, starts 1941–1993")
        for xi, v in zip(x, oos):
            ax.text(xi + 0.19, v + 0.04, f"{v:.2f}", ha="center", fontsize=8.5)
        for xi, v in zip(x, ins):
            if v is not None:
                ax.text(xi - 0.19, v + 0.04, f"{v:.2f}", ha="center", fontsize=8.5, color=MUTED)
        ax.set_xticks(x, labels, fontsize=8.5); ax.set_ylim(3, 5.3)
        ax.set_title(f"Stocks + {safe}", loc="left", fontsize=11, color=INK)
        ax.grid(axis="y", color=GRID, lw=0.8)
    axes[0].set_ylabel("SAFEMAX (%)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.suptitle("Optimising the stock shares by valuation: worst-case safe rate", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "optimisation.png", dpi=150)


def timeline():
    d = V.load()
    yrs = d.index[d["cape_rel"].notna()]
    rel = d.loc[yrs, "cape_rel"]
    share = np.where(rel < 2 / 3, 1.0, np.where(rel > 4 / 3, 0.0, 0.55))
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, gridspec_kw={"height_ratios": [1.3, 1]})
    ax = axes[0]
    ax.plot(yrs, rel, color=INK, lw=1.4)
    ax.axhline(4 / 3, color=BAD, lw=1, ls="--"); ax.axhline(2 / 3, color=ACCENT, lw=1, ls="--")
    ax.text(1882, 4 / 3 + 0.06, "expensive: above 4/3 of median", color=BAD, fontsize=8.5)
    ax.text(1882, 2 / 3 - 0.2, "cheap: below 2/3 of median", color=ACCENT, fontsize=8.5)
    ax.set_ylabel("CAPE ÷ its median to date"); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_title("Optimised rule (stocks + bills): 100% stocks when cheap, 55% when fair, 0% when expensive",
                 loc="left", fontsize=11, color=INK)
    ax = axes[1]
    ax.fill_between(yrs, share * 100, step="post", color=ACCENT, alpha=0.35, lw=0)
    ax.step(yrs, share * 100, where="post", color=ACCENT, lw=1.2)
    ax.set_ylabel("Stock share (%)"); ax.set_ylim(0, 105); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.annotate("expensive in 89% of\nJanuaries since 1995", xy=(2016, 4), xytext=(1997, 72), fontsize=8.5,
                arrowprops=dict(arrowstyle="->", color=MUTED), color=INK)
    fig.tight_layout(); fig.savefig(OUT / "timeline.png", dpi=150)


def pfau_oos():
    c = pd.read_csv(OUT / "pfau2011_out_of_sample.csv", index_col=0)
    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(c.index, c["actual MWR %"], color=INK, lw=2, marker="o", ms=4, label="What happened")
    ax.plot(c.index, c["predicted MWR %"], color=ACCENT, lw=2, ls="--", marker="o", ms=4,
            label="Predicted from CAPE, dividend yield and bond yield")
    ax.set_ylabel("Highest 30-year withdrawal rate, 60/40 (%)"); ax.set_ylim(0, 12)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Pfau (2011) model fitted on 1883–1980 starts: too pessimistic for 1981–1993 retirees", loc="left",
                 fontsize=11, color=INK)
    fig.tight_layout(); fig.savefig(OUT / "pfau2011_out_of_sample.png", dpi=150)


if __name__ == "__main__":
    reproduction(); optimisation(); timeline(); pfau_oos()
