"""Chart: the Shiller-ECY stock rule against 100% stocks and the plan's fixed 80% (output/valuation/vs100_*.png)."""
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
from bengen import stockrule as sr  # noqa: E402
import valuation_best as vb  # noqa: E402

OUT = ROOT / "output" / "valuation"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e5e4df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
RULES = [("100% stocks", sr.Rule("none", 1.0), "#c0703a"),
         ("Fixed 80% (the plan)", sr.Rule("none", 0.8), "#b9b8b2"),
         ("Shiller-ECY rule, 50–100%", sr.Rule("ecys", 0.8, 1, 1.0, 0.5), "#2a78d6")]
SETS = [("1928-2025", "Reshuffled\n1928–2025"), ("1881-2022", "Reshuffled\n1881–2022"),
        ("1928-1976 only", "Only years\n1928–1976"), ("1977-2025 only", "Only years\n1977–2025")]
RATE = 0.065


def bars(ax, vals, fmt, title, ylabel, ylim):
    x = np.arange(len(SETS)); w = 0.27
    for k, (name, _, c) in enumerate(RULES):
        v = vals[name]
        ax.bar(x + (k - 1) * w, v, w * 0.92, color=c, label=name)
        for xi, vi in zip(x, v):
            ax.text(xi + (k - 1) * w, vi + (ylim[1] - ylim[0]) * 0.012, fmt.format(vi), ha="center", fontsize=7.5,
                    color=MUTED)
    ax.set_xticks(x, [s for _, s in SETS], fontsize=8.5); ax.set_ylim(*ylim)
    ax.set_title(title, loc="left", fontsize=11, color=INK); ax.set_ylabel(ylabel); ax.grid(axis="y", color=GRID, lw=0.8)


def main():
    dp, dl = vb.frame("plan"), vb.frame("long")
    sets = {"1928-2025": vb.Set.boot(dp), "1881-2022": vb.Set.boot(dl),
            "1928-1976 only": vb.Set.boot(dp, (1928, 1976)), "1977-2025 only": vb.Set.boot(dp, (1977, 2025))}
    rate, runout, rows = {}, {}, []
    paths = {}
    for name, rule, _ in RULES:
        rate[name], runout[name] = [], []
        for sn, st in sets.items():
            W = sr.shares(rule, st.X[rule.signal])
            r = sr.rate_at(vb.P, W, st.S, st.B, st.I)
            o = sr.simulate(replace(vb.P, rate=RATE), W, st.S, st.B, st.I)
            rate[name].append(r * 100); runout[name].append(o["depleted"].mean() * 100)
            if sn == "1928-2025":
                # balance path: rerun tracking the real balance
                paths[name] = (o["reals"] * 100, o["final"] * 100, W)
            rows.append({"rule": name, "set": sn, "rate_at_2pct": r * 100, "runout_at_6.5": runout[name][-1]})
    pd.DataFrame(rows).to_csv(OUT / "vs100.csv", index=False)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    bars(axes[0, 0], rate, "{:.2f}", "Highest starting rate with only 2% running out", "% of starting portfolio", (4, 8.7))
    bars(axes[0, 1], runout, "{:.1f}", "Share running out at the plan's 6.5% start", "% of retirements", (0, 9.5))
    axes[0, 0].legend(frameon=False, fontsize=8.5, loc="upper left")
    yrs = np.arange(1, 31)
    ax = axes[1, 0]
    for name, _, c in RULES:
        reals = paths[name][0]
        ax.plot(yrs, np.median(reals, axis=0), color=c, lw=2.2, label=f"{name}, typical")
        ax.plot(yrs, np.percentile(reals, 10, axis=0), color=c, lw=1.4, ls="--")
    ax.set_title("Spending at a 6.5% start: typical (solid) and unlucky 10% (dashed)", loc="left", fontsize=11, color=INK)
    ax.set_xlabel("Year of retirement"); ax.set_ylabel(r"Real spending, \$ per \$100 saved"); ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_ylim(0, 8)
    ax = axes[1, 1]
    for name, _, c in RULES:
        f = np.sort(paths[name][1])
        ax.plot(np.linspace(0, 100, len(f)), f, color=c, lw=2.2, label=name)
    ax.set_yscale("symlog", linthresh=10); ax.set_ylim(0, 3000); ax.set_yticks([0, 10, 50, 100, 200, 500, 1000]); ax.set_yticklabels(["0", "10", "50", "100", "200", "500", "1,000"])
    ax.set_title("Money left after 30 years at a 6.5% start, every retiree", loc="left", fontsize=11, color=INK)
    ax.set_xlabel("Retirees ranked from least to most left (percentile)"); ax.set_ylabel(r"Real \$ per \$100 saved")
    ax.grid(color=GRID, lw=0.6)
    for name, _, c in RULES:
        f = paths[name][1]
        print(name, "median final", round(np.median(f)), "p10", round(np.percentile(f, 10)), "p90", round(np.percentile(f, 90)),
              "typ 1-10", round(np.median(paths[name][0][:, :10].mean(1)), 2), "p10 spend yr", round(np.percentile(paths[name][0], 10), 2),
              "avg stocks", round(paths[name][2].mean() * 100))
    fig.suptitle("Shiller-ECY stock rule vs 100% stocks, inside the recommended plan (30% of stocks international)",
                 x=0.01, ha="left", fontsize=13)
    fig.tight_layout(); fig.savefig(OUT / "vs100.png", dpi=150)
    print(pd.DataFrame(rows).round(2))


if __name__ == "__main__":
    main()
