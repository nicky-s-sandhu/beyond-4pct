"""Interactive dashboard: tune the recommended withdrawal plan and see 69 historical retirements.

Run:
    pip install -r app/requirements.txt
    python app/dashboard.py            # then open http://127.0.0.1:8050

Every control starts at the recommended plan from the write-up. Each change re-simulates all
69 thirty-year retirements (1928-1996 starts) with the project's engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figures as F  # noqa: E402
import model  # noqa: E402

INK, MUTED, GRID, ACCENT, BAD, GOOD = "#0b0b0b", "#52514e", "#e5e4df", "#2a78d6", "#a23b2a", "#1d7a3a"

# id, label, min, max, step, help text
SLIDERS = {
    "Spending": [
        ("rate", "Starting withdrawal rate (%)", 2.0, 10.0, 0.1, "First-year spending as % of the portfolio"),
        ("drift", "Planned real change per year (%)", -4.0, 1.0, 0.1, "Negative = spending planned to decline"),
        ("floor", "Spending floor (%)", 0, 100, 5, "Never spend below this; 0 = no floor"),
        ("ceiling", "Spending cap (× plan)", 0.0, 3.0, 0.1, "0 = no cap"),
    ],
    "Yearly adjustments": [
        ("band", "No-change band (± % of start rate)", 0.0, 30.0, 0.1, "Adjust only when the withdrawal rate "
                                                                       "moves this far from the start rate"),
        ("cut_step", "Cut size (%)", 0.0, 35.0, 0.5, "Real cut when the withdrawal rate is too high"),
        ("raise_step", "Raise size (%)", 0.0, 35.0, 0.1, "Real raise when the withdrawal rate is low"),
    ],
    "Portfolio": [
        ("stocks", "Stocks (%)", 20, 100, 1, "Rest in bonds (and cash, if any)"),
        ("intl", "International share of stocks (%)", 0, 50, 1, "Developed markets outside the US"),
    ],
    "Cash bucket (optional)": [
        ("cash", "Cash (% of portfolio, from bonds)", 0, 25, 1, "Spent first in downturns; 0 = off"),
        ("threshold", "Downturn trigger (% below peak)", 0, 30, 1, ""),
        ("max_years", "Max years funded from cash/bonds", 1, 8, 1, ""),
        ("refill_years", "Refill over (up years)", 1, 8, 1, ""),
    ],
}
RADIOS = [
    ("floor_mode", "Floor measured against", [("fixed", "First-year spending"), ("plan", "The declining plan")]),
    ("bonds", "Bonds", [("intermediate", "Intermediate (½ bills + ½ 10-yr)"), ("10y", "10-year Treasury")]),
    ("intl_series", "International data", [("intl", "Base"), ("intl_stress", "Pessimistic (war losses)")]),
    ("who", "Score weights years by", [("couple", "Couple alive"), ("single", "Single person alive"),
                                       ("none", "Equal weight")]),
]
SLIDER_IDS = [s[0] for group in SLIDERS.values() for s in group]
CONTROL_IDS = SLIDER_IDS + [r[0] for r in RADIOS] + ["gamma"]


def slider(id_, label, lo, hi, step, help_):
    marks = {lo: f"{lo:g}", hi: f"{hi:g}"}
    return html.Div([
        html.Div([html.Span(label, style={"fontWeight": 500}),
                  html.Span(help_, style={"color": MUTED, "fontSize": 11, "display": "block"})]),
        dcc.Slider(id=id_, min=lo, max=hi, step=step, value=model.RECOMMENDED[id_], marks=marks,
                   tooltip={"placement": "bottom", "always_visible": True}, updatemode="mouseup"),
    ], style={"marginBottom": 14})


def radio(id_, label, options):
    return html.Div([
        html.Div(label, style={"fontWeight": 500, "marginBottom": 4}),
        dcc.RadioItems(id=id_, options=[{"label": l, "value": v} for v, l in options],
                       value=model.RECOMMENDED[id_], labelStyle={"display": "block", "fontSize": 13},
                       inputStyle={"marginRight": 6}),
    ], style={"marginBottom": 14})


def controls():
    blocks = [
        html.H2("Settings", style={"fontSize": 18, "margin": "0 0 8px"}),
        html.Div("Start from a preset, then tune.", style={"color": MUTED, "fontSize": 13, "marginBottom": 8}),
        dcc.Dropdown(id="preset", options=list(model.PRESETS), value="Recommended plan", clearable=False),
        html.Button("Reset to recommended plan", id="reset", n_clicks=0,
                    style={"margin": "8px 0 16px", "width": "100%", "padding": "8px", "border": f"1px solid {GRID}",
                           "background": "white", "borderRadius": 6, "cursor": "pointer"}),
    ]
    for group, items in SLIDERS.items():
        blocks.append(html.H3(group, style={"fontSize": 14, "margin": "18px 0 10px", "color": ACCENT}))
        blocks += [slider(*it) for it in items]
        if group == "Spending":
            blocks.append(radio(*RADIOS[0]))
    blocks.append(html.H3("Data and scoring", style={"fontSize": 14, "margin": "18px 0 10px", "color": ACCENT}))
    blocks += [radio(*r) for r in RADIOS[1:]]
    blocks.append(html.Div([
        html.Div("Risk aversion (how much cuts count)", style={"fontWeight": 500}),
        dcc.Slider(id="gamma", min=1.5, max=6, step=0.5, value=model.RECOMMENDED["gamma"],
                   marks={1.5: "1.5", 3: "3", 6: "6"}, tooltip={"placement": "bottom", "always_visible": True}),
    ]))
    return html.Div(blocks, className="sidebar")


def tile(label, value, sub=None, color=INK):
    return html.Div([
        html.Div(label, style={"fontSize": 12, "color": MUTED}),
        html.Div(value, style={"fontSize": 22, "fontWeight": 600, "color": color}),
        html.Div(sub or "", style={"fontSize": 11, "color": MUTED}),
    ], style={"padding": "10px 12px", "border": f"1px solid {GRID}", "borderRadius": 8, "background": "white"})


def delta(v, ref, fmt, higher_is_better=True):
    d = v - ref
    if abs(d) < 1e-9:
        return "same as recommended"
    better = (d > 0) == higher_is_better
    return html.Span(f"{'+' if d > 0 else '−'}{fmt(abs(d))} vs recommended", style={"color": GOOD if better else BAD})


app = Dash(__name__, title="Withdrawal plan explorer")
app.layout = html.Div([
    html.Div([
        html.H1("Withdrawal plan explorer", style={"fontSize": 22, "margin": 0}),
        html.Div("Tune the recommended plan and see how it would have done for every 30-year retirement starting "
                 "1928–1996. Dollar figures are real spending per $100 of starting portfolio.",
                 style={"color": MUTED, "fontSize": 13, "marginTop": 4}),
    ], style={"padding": "14px 20px", "borderBottom": f"1px solid {GRID}"}),
    html.Div([
        controls(),
        html.Div([
            html.Div(id="warning"),
            html.Div(id="tiles", className="tiles"),
            dcc.Graph(id="paths", config={"displaylogo": False}),
            html.Div([dcc.Graph(id="pain", config={"displaylogo": False})]),
            dcc.Graph(id="years", config={"displaylogo": False}),
            html.Div([
                html.Span("Explore one retiree, starting in ", style={"color": MUTED}),
                dcc.Dropdown(id="year", options=[{"label": str(y), "value": y} for y in range(1928, 1997)],
                             value=1966, clearable=False, style={"width": 110, "display": "inline-block",
                                                                 "verticalAlign": "middle"}),
            ], style={"margin": "8px 0"}),
            dcc.Graph(id="retiree", config={"displaylogo": False}),
            html.Div("Historical backtest of US stocks and bonds with developed-market stocks, 1928–2025. "
                     "No fees or taxes. Not financial advice.", style={"color": MUTED, "fontSize": 12,
                                                                        "margin": "12px 0 24px"}),
        ], className="main"),
    ], className="layout"),
], style={"fontFamily": "Inter, -apple-system, Segoe UI, Roboto, sans-serif", "color": INK, "background": "white"})


@app.callback([Output(c, "value") for c in CONTROL_IDS], Input("preset", "value"), Input("reset", "n_clicks"))
def apply_preset(preset, _):
    name = "Recommended plan" if ctx.triggered_id == "reset" else preset
    s = model.PRESETS[name]
    return [s[c] for c in CONTROL_IDS]


@app.callback(Output("preset", "value"), Input("reset", "n_clicks"), prevent_initial_call=True)
def reset_preset(_):
    return "Recommended plan"


def settings_from(values):
    return dict(zip(CONTROL_IDS, values))


@app.callback(Output("tiles", "children"), Output("warning", "children"), Output("paths", "figure"),
              Output("pain", "figure"), Output("years", "figure"),
              [Input(c, "value") for c in CONTROL_IDS])
def update(*values):
    s = settings_from(values)
    ref_s = {**model.RECOMMENDED, "bonds": s["bonds"], "intl_series": s["intl_series"], "who": s["who"],
             "gamma": s["gamma"]}
    r, ref = model.run(s), model.run(ref_s)
    m, rm = r.m, ref.m
    money = lambda v: f"${v:.2f}"
    tiles = [
        tile("Smooth-spending score", money(m["ce"]), delta(m["ce"], rm["ce"], money)),
        tile("Typical spending, yrs 1–10", money(m["typical_1_10"]),
             delta(m["typical_1_10"], rm["typical_1_10"], money)),
        tile("Typical spending, yrs 11–20", money(m["typical_11_20"]),
             delta(m["typical_11_20"], rm["typical_11_20"], money)),
        tile("Typical spending, yrs 21–30", money(m["typical_21_30"]),
             delta(m["typical_21_30"], rm["typical_21_30"], money)),
        tile("Ran out of money", f"{m['ran_out']} of {len(r.starts)}",
             delta(m["ran_out"], rm["ran_out"], lambda v: f"{v:.0f}", higher_is_better=False),
             color=BAD if m["ran_out"] else INK),
        tile("Big drop: ≥30% below year 1", f"{m['big_drop_share']:.0%}",
             delta(m["big_drop_share"] * 100, rm["big_drop_share"] * 100, lambda v: f"{v:.0f} pts",
                   higher_is_better=False)),
        tile("Gave back ≥30% from best year", f"{m['give_back_share']:.0%}",
             delta(m["give_back_share"] * 100, rm["give_back_share"] * 100, lambda v: f"{v:.0f} pts",
                   higher_is_better=False)),
        tile("Median ending balance", f"${m['median_final']:.0f}", "per $100 started, real"),
    ]
    warn = None
    if m["extreme_share"] > 0.10:
        warn = html.Div(f"Breaks the study's limit: {m['extreme_share']:.0%} of retirees had an extreme cut "
                        f"(50%+ below plan) or ran out, above the 10% allowed.",
                        style={"background": "#fbeae6", "color": BAD, "padding": "8px 12px", "borderRadius": 6,
                               "marginBottom": 10, "fontSize": 13})
    return tiles, warn, F.spending_paths(r, ref), F.pain_levels(r, ref), F.by_start_year(r)


@app.callback(Output("retiree", "figure"), Input("year", "value"), [Input(c, "value") for c in CONTROL_IDS])
def update_retiree(year, *values):
    return F.retiree(model.run(settings_from(values)), year)


server = app.server  # for gunicorn etc.

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    app.run(host=a.host, port=a.port, debug=a.debug)
