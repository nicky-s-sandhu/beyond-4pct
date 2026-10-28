"""Plotly figures for the dashboard. Each takes model.Result objects and returns a Figure."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from model import LEVELS, level_shares

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e5e4df"
ACCENT, BAND, GHOST, BAD = "#2a78d6", "#86b6ef", "#8a8984", "#7f2f14"
LCOL = {"None": "#dcdbd5", "Mild": "#eda07a", "Moderate": "#dd7646", "Severe": "#bb5228", "Extreme": "#7f2f14",
        "Ran out": "#2b2a27"}
LLAB = {"None": "None (<5%)", "Mild": "Mild (5–15%)", "Moderate": "Moderate (15–30%)", "Severe": "Severe (30–50%)",
        "Extreme": "Extreme (≥50%)", "Ran out": "Ran out of money"}
FONT = dict(family="Inter, -apple-system, Segoe UI, Roboto, sans-serif", size=12, color=INK)


def _base(fig, title, height):
    fig.update_layout(title=dict(text=title, x=0.01, xanchor="left", font=dict(size=14)), height=height,
                      font=FONT, paper_bgcolor="white", plot_bgcolor="white", margin=dict(l=60, r=20, t=60, b=50),
                      hoverlabel=dict(bgcolor="white", font_size=12), legend=dict(orientation="h", y=-0.18, x=0))
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    return fig


def spending_paths(r, ref=None):
    """Median, 10th-90th band, unluckiest retiree, plan and floor; recommended median as a reference."""
    yrs = np.arange(1, r.reals.shape[1] + 1)
    lo, med, hi = (np.percentile(r.reals, q, axis=0) for q in (10, 50, 90))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=yrs, y=hi, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=yrs, y=lo, fill="tonexty", fillcolor="rgba(134,182,239,0.45)", line=dict(width=0),
                             name="10th–90th percentile", customdata=np.stack([lo, hi], axis=1),
                             hovertemplate="Year %{x}: 10th–90th percentile $%{customdata[0]:.2f}–"
                                           "$%{customdata[1]:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=yrs, y=r.plan, name="Plan", line=dict(color=MUTED, width=1.4, dash="dot"),
                             hovertemplate="Year %{x}: plan $%{y:.2f}<extra></extra>"))
    if r.params.ceiling > 0:
        fig.add_trace(go.Scatter(x=yrs, y=r.plan * r.params.ceiling, name="Cap", line=dict(color=MUTED, width=1),
                                 hovertemplate="Year %{x}: cap $%{y:.2f}<extra></extra>"))
    if r.floor.any():
        fig.add_trace(go.Scatter(x=yrs, y=r.floor, name="Floor", line=dict(color=INK, width=1, dash="dash"),
                                 hovertemplate="Year %{x}: floor $%{y:.2f}<extra></extra>"))
    if ref is not None:
        fig.add_trace(go.Scatter(x=yrs, y=np.median(ref.reals, axis=0), name="Recommended plan: median",
                                 line=dict(color=GHOST, width=1.6, dash="dash"),
                                 hovertemplate="Year %{x}: recommended median $%{y:.2f}<extra></extra>"))
    u = r.m["unluckiest"]
    fig.add_trace(go.Scatter(x=yrs, y=r.reals[u], name=f"Unluckiest retiree ({r.starts[u]} start)",
                             line=dict(color=BAD, width=1.6, dash="longdash"),
                             hovertemplate=f"{r.starts[u]} start, year %{{x}}: $%{{y:.2f}}<extra></extra>"))
    fig.add_trace(go.Scatter(x=yrs, y=med, name="Median retiree", line=dict(color=ACCENT, width=3),
                             hovertemplate="Year %{x}: median $%{y:.2f}<extra></extra>"))
    fig.update_xaxes(title_text="Year of retirement", dtick=5)
    fig.update_yaxes(title_text="Real spending per $100 saved ($)", rangemode="tozero")
    fig = _base(fig, "Spending over 30 years (real $ per $100 of starting portfolio)", 460)
    fig.update_layout(legend=dict(orientation="h", y=-0.26, x=0), margin=dict(b=100))
    return fig


def pain_levels(r, ref=None):
    """Stacked bars of cut severity, below plan and from best year, for this plan and the recommended one."""
    rows = [("This plan", r)] + ([("Recommended", ref)] if ref is not None else [])
    labels, shares = [], []
    for name, res in rows:
        for measure, lv in (("below plan", res.m["levels"]), ("from best year", res.m["levels_best"])):
            labels.append(f"{name}: {measure}")
            shares.append(level_shares(lv))
    fig = go.Figure()
    for lv in LEVELS:
        vals = [s[lv] * 100 for s in shares]
        fig.add_trace(go.Bar(y=labels, x=vals, orientation="h", name=LLAB[lv], marker_color=LCOL[lv],
                             marker_line=dict(color="white", width=1.5),
                             marker_pattern_shape="/" if lv == "Ran out" else "",
                             text=[f"{v:.0f}%" if v >= 7 else "" for v in vals], textposition="inside",
                             insidetextanchor="middle",
                             textfont=dict(color="white" if lv in ("Severe", "Extreme", "Ran out") else INK),
                             hovertemplate="%{y}<br>" + LLAB[lv] + ": %{x:.0f}% of retirees<extra></extra>"))
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_xaxes(range=[0, 100], ticksuffix="%", title_text="Share of 69 historical retirees")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig = _base(fig, "Deepest spending cut each retiree lived through", 340)
    fig.update_layout(legend=dict(orientation="h", y=-0.32, x=0, traceorder="normal"), margin=dict(b=90))
    return fig


def by_start_year(r):
    """Lowest real spending for each retirement start year; ran-out years highlighted."""
    lowest = r.reals.min(axis=1)
    early = r.reals[:, :10].mean(axis=1)
    fig = go.Figure(go.Bar(
        x=r.starts, y=lowest, marker_color=ACCENT, name="Lowest year",
        customdata=np.stack([early, r.balance[:, -1], r.ran_out.astype(int)], axis=1),
        hovertemplate="Retired %{x}<br>Lowest year: $%{y:.2f}<br>Average yrs 1–10: $%{customdata[0]:.2f}"
                      "<br>Ending balance: $%{customdata[1]:.0f}<extra></extra>"))
    out_years = [y for y, ro in zip(r.starts, r.ran_out) if ro]
    if out_years:
        # spending hits $0 for these retirees, so a bar would be invisible: mark them explicitly
        when = [int(np.argmax(r.reals[r.starts.index(y)] < 1e-9)) + 1 for y in out_years]
        fig.add_trace(go.Scatter(x=out_years, y=[0.25] * len(out_years), mode="markers",
                                 marker=dict(symbol="x", size=11, color=BAD, line=dict(width=2)),
                                 name="Ran out of money", customdata=when,
                                 hovertemplate="Retired %{x}: ran out in year %{customdata}<extra></extra>"))
    if r.floor.any():
        fig.add_hline(y=float(r.floor.min()), line=dict(color=INK, width=1, dash="dash"),
                      annotation_text="lowest floor", annotation_position="top left",
                      annotation_font=dict(color=MUTED, size=11))
    fig.update_xaxes(title_text="Retirement start year", dtick=10)
    fig.update_yaxes(title_text="Lowest yearly spending ($ per $100)", rangemode="tozero")
    n_out = int(r.ran_out.sum())
    title = "Lowest yearly spending by start year" + (f" · {n_out} ran out (marked ×)" if n_out else " · none ran out")
    fig = _base(fig, title, 330)
    fig.update_layout(showlegend=False)
    return fig


def retiree(r, year):
    """One retiree's spending and portfolio balance, stacked (no dual axis)."""
    k = r.starts.index(year)
    yrs = np.arange(1, r.reals.shape[1] + 1)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12, row_heights=[0.55, 0.45],
                        subplot_titles=("Real spending ($ per $100 saved)", "Portfolio at year end (real $)"))
    fig.add_trace(go.Bar(x=yrs, y=r.reals[k], marker_color=ACCENT, name="Spending",
                         hovertemplate="Year %{x}: $%{y:.2f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=yrs, y=r.plan, name="Plan", line=dict(color=MUTED, dash="dot"),
                             hovertemplate="Year %{x}: plan $%{y:.2f}<extra></extra>"), row=1, col=1)
    if r.params.ceiling > 0:
        fig.add_trace(go.Scatter(x=yrs, y=r.plan * r.params.ceiling, name="Cap", line=dict(color=MUTED, width=1),
                                 hovertemplate="Year %{x}: cap $%{y:.2f}<extra></extra>"), row=1, col=1)
    if r.floor.any():
        fig.add_trace(go.Scatter(x=yrs, y=r.floor, name="Floor", line=dict(color=INK, width=1, dash="dash"),
                                 hovertemplate="Year %{x}: floor $%{y:.2f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=yrs, y=r.balance[k], fill="tozeroy", fillcolor="rgba(134,182,239,0.35)",
                             line=dict(color=ACCENT, width=2), name="Portfolio",
                             hovertemplate="Year %{x}: $%{y:.0f}<extra></extra>"), row=2, col=1)
    fig.update_xaxes(title_text="Year of retirement", row=2, col=1, dtick=5)
    fig.update_yaxes(rangemode="tozero")
    for a in fig.layout.annotations:
        a.update(x=0, xanchor="left", font=dict(size=12, color=MUTED))
    status = "ran out of money" if r.ran_out[k] else f"ended with ${r.balance[k, -1]:.0f}"
    fig = _base(fig, f"One retiree: started in {year} · {status}", 460)
    fig.update_layout(showlegend=False)
    return fig
