/* Withdrawal plan explorer: controls and charts (static port of app/dashboard.py and app/figures.py). */
(function () {
  "use strict";
  const C = { ink: "#0b0b0b", muted: "#52514e", grid: "#e5e4df", accent: "#2a78d6", band: "rgba(134,182,239,0.45)",
              ghost: "#8a8984", bad: "#7f2f14", good: "#1d7a3a" };
  const LCOL = { None: "#dcdbd5", Mild: "#eda07a", Moderate: "#dd7646", Severe: "#bb5228", Extreme: "#7f2f14",
                 "Ran out": "#2b2a27" };
  const LLAB = { None: "None (<5%)", Mild: "Mild (5–15%)", Moderate: "Moderate (15–30%)", Severe: "Severe (30–50%)",
                 Extreme: "Extreme (≥50%)", "Ran out": "Ran out of money" };
  const FONT = { family: "Inter, -apple-system, Segoe UI, Roboto, sans-serif", size: 12, color: C.ink };
  const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["select2d", "lasso2d"] };

  // [id, label, min, max, step, help, unit]
  const SLIDERS = {
    "Spending": [
      ["rate", "Starting withdrawal rate", 2, 10, 0.1, "First-year spending as % of the portfolio", "%"],
      ["drift", "Fixed real change per year", -4, 1, 0.1, "Used when the spending path is a fixed yearly change", "%"],
      ["floor", "Spending floor", 0, 100, 1, "Never spend below this share of year 1; 0 = no floor", "%"],
      ["ceiling", "Spending cap (× plan)", 0, 3, 0.05, "1.1 = never more than 10% above the plan; 0 = no cap", "×"],
    ],
    "Yearly adjustments": [
      ["band", "No-change band (± % of start rate)", 0, 30, 0.1, "Adjust only when the withdrawal rate moves this far from the start rate", "%"],
      ["cut_step", "Cut size", 0, 35, 0.5, "Real cut when the withdrawal rate is too high", "%"],
      ["raise_step", "Raise size", 0, 35, 0.1, "Real raise when the withdrawal rate is low", "%"],
    ],
    "Portfolio": [
      ["stocks", "Stocks", 20, 100, 1, "Rest in bonds (and cash, if any)", "%"],
      ["intl", "International share of stocks", 0, 50, 1, "Developed markets outside the U.S.", "%"],
    ],
    "Cash bucket (optional)": [
      ["cash", "Cash (% of portfolio, from bonds)", 0, 25, 1, "Spent first in downturns; 0 = off", "%"],
      ["threshold", "Downturn trigger (% below peak)", 0, 30, 1, "", "%"],
      ["max_years", "Max years funded from cash/bonds", 1, 8, 1, "", ""],
      ["refill_years", "Refill over (up years)", 1, 8, 1, "", ""],
    ],
  };
  const RADIOS = {
    curve: ["Planned spending path", [["blanchett", "Retirees' actual pattern (Blanchett 2014, about −1%/yr)"],
                                       ["fixed", "Fixed yearly change (slider below)"]]],
    floor_mode: ["Floor measured against", [["fixed", "First-year spending"], ["plan", "The declining plan"]]],
    bonds: ["Bonds", [["intermediate", "Intermediate (½ bills + ½ 10-yr)"], ["10y", "10-year Treasury"]]],
    intl_series: ["International data", [["intl", "Base"], ["intl_stress", "Pessimistic (war losses)"]]],
    who: ["Score weights years by", [["couple", "Couple alive"], ["single", "Single person alive"], ["none", "Equal weight"]]],
  };

  let DATA, ENGINE, REC, state;
  const $ = id => document.getElementById(id);
  const money = v => "$" + v.toFixed(2);
  const fmtVal = (v, unit) => (unit === "×" ? (+v).toFixed(2) + "×" : (+v).toFixed(Number.isInteger(+v) ? 0 : 1) + (unit === "%" ? "%" : ""));

  function percentile(sorted, q) {            // numpy's default (linear) percentile on sorted values
    const pos = (sorted.length - 1) * q / 100, lo = Math.floor(pos), hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  const yrs = Array.from({ length: 30 }, (_, i) => i + 1);
  const column = (r, t) => Array.from({ length: r.n }, (_, i) => r.reals(i, t)).sort((a, b) => a - b);

  function base(title, height, extra) {
    const narrow = window.innerWidth < 640;
    if (narrow) title = title.replace(" · ", "<br>").replace(" (real $ per $100 of starting portfolio)", "<br>(real $ per $100 saved)");
    return Object.assign({
      title: { text: title, x: 0.01, xanchor: "left", font: { size: narrow ? 13 : 14 } }, height: height, font: FONT,
      paper_bgcolor: "white", plot_bgcolor: "white", margin: { l: 60, r: 20, t: 60, b: 50 },
      hoverlabel: { bgcolor: "white", font: { size: 12 } }, legend: { orientation: "h", y: -0.18, x: 0 },
      xaxis: { showgrid: false, linecolor: C.grid, tickfont: { color: C.muted }, title: { font: { color: C.muted } } },
      yaxis: { gridcolor: C.grid, zeroline: false, tickfont: { color: C.muted }, title: { font: { color: C.muted } } },
    }, extra || {});
  }

  // ---------- controls ----------
  function buildControls() {
    const box = $("controls");
    const slider = ([id, label, lo, hi, step, help, unit]) => {
      const d = document.createElement("div");
      d.className = "ctl";
      d.innerHTML = `<div class="top"><span class="lab"><label for="${id}">${label}</label>${Help.icon(id, label)}</span>` +
        `<output id="${id}-out"></output></div>` +
        (help ? `<div class="hint">${help}</div>` : "") +
        `<input type="range" id="${id}" min="${lo}" max="${hi}" step="${step}">`;
      const inp = d.querySelector("input");
      inp.dataset.unit = unit;
      inp.addEventListener("input", () => { state[id] = +inp.value; showValue(id); schedule(); });
      return d;
    };
    const radio = id => {
      const [title, opts] = RADIOS[id];
      const d = document.createElement("div");
      d.className = "ctl radio";
      d.innerHTML = `<div class="title">${title}${Help.icon(id, title)}</div>` + opts.map(([v, l]) =>
        `<label><input type="radio" name="${id}" value="${v}"> ${l}</label>`).join("");
      d.querySelectorAll("input").forEach(inp => inp.addEventListener("change", () => { state[id] = inp.value; schedule(); }));
      return d;
    };
    for (const [group, items] of Object.entries(SLIDERS)) {
      const h = document.createElement("h3"); h.textContent = group; box.appendChild(h);
      items.forEach((it, i) => {
        if (group === "Spending" && i === 1) box.appendChild(radio("curve"));
        box.appendChild(slider(it));
      });
      if (group === "Spending") box.appendChild(radio("floor_mode"));
    }
    const h = document.createElement("h3"); h.textContent = "Data and scoring"; box.appendChild(h);
    ["bonds", "intl_series", "who"].forEach(id => box.appendChild(radio(id)));
    box.appendChild(slider(["gamma", "Risk aversion (how much cuts count)", 1.5, 6, 0.5, "Used only for the smooth-spending score", ""]));

    $("preset-help").innerHTML = Help.icon("preset");
    $("year-help").innerHTML = Help.icon("year");
    const sel = $("preset");
    Object.keys(DATA.presets).forEach(k => { const o = document.createElement("option"); o.value = o.textContent = k; sel.appendChild(o); });
    sel.addEventListener("change", () => applyPreset(sel.value));
    $("reset").addEventListener("click", () => { sel.value = "Recommended plan"; applyPreset("Recommended plan"); });
    $("share").addEventListener("click", copyLink);
    const ys = $("year");
    ENGINE.starts.forEach(y => { const o = document.createElement("option"); o.value = o.textContent = y; ys.appendChild(o); });
    ys.value = 1966;
    ys.addEventListener("change", drawRetiree);
  }

  function showValue(id) {
    const inp = $(id), out = $(id + "-out");
    out.textContent = fmtVal(state[id], inp.dataset.unit);
    out.classList.toggle("changed", Math.abs(state[id] - REC[id]) > 1e-9);
  }

  function syncControls() {
    document.querySelectorAll(".ctl input[type=range]").forEach(inp => { inp.value = state[inp.id]; showValue(inp.id); });
    Object.keys(RADIOS).forEach(id => document.querySelectorAll(`input[name=${id}]`).forEach(r => { r.checked = r.value === state[id]; }));
  }

  function applyPreset(name) { state = Object.assign({}, DATA.presets[name]); syncControls(); update(); }

  function copyLink() {
    const diff = {};
    Object.keys(state).forEach(k => { if (state[k] !== REC[k]) diff[k] = state[k]; });
    const url = location.origin + location.pathname + (Object.keys(diff).length ? "#" + encodeURIComponent(JSON.stringify(diff)) : "");
    try { history.replaceState(null, "", url); } catch (e) { /* ignore */ }
    const btn = $("share"), done = t => { btn.textContent = t; setTimeout(() => { btn.textContent = "Copy a link to these settings"; }, 1800); };
    try {
      navigator.clipboard.writeText(url).then(() => done("Link copied"), () => done("Link is in the address bar"));
    } catch (e) { done("Link is in the address bar"); }
  }

  function fromHash() {
    try {
      if (location.hash.length > 1) {
        const diff = JSON.parse(decodeURIComponent(location.hash.slice(1)));
        Object.keys(diff).forEach(k => { if (k in REC) state[k] = diff[k]; });
        $("preset").value = "Recommended plan";
      }
    } catch (e) { /* bad link: keep defaults */ }
  }

  let pending = null;
  function schedule() { if (pending) cancelAnimationFrame(pending); pending = requestAnimationFrame(() => { pending = null; update(); }); }

  // ---------- tiles ----------
  function delta(v, ref, fmt, higherBetter) {
    const d = v - ref;
    if (Math.abs(d) < 1e-9) return ["same as recommended", ""];
    const better = (d > 0) === (higherBetter !== false);
    return [(d > 0 ? "+" : "−") + fmt(Math.abs(d)) + " vs recommended", better ? "good" : "bad"];
  }
  const TILE_HELP = { "Smooth-spending score": "t_score", "Typical spending, yrs 1–10": "t_typ1",
    "Typical spending, yrs 11–20": "t_typ2", "Typical spending, yrs 21–30": "t_typ3", "Ran out, real history": "t_hist",
    "Ran out, reshuffled history": "t_boot", "Gave back ≥30% from best year": "t_give", "Median ending balance": "t_end" };
  function tile(k, v, d, vClass) {
    const [txt, cls] = Array.isArray(d) ? d : [d || "", ""];
    return `<div class="tile"><div class="k">${k}${TILE_HELP[k] ? Help.icon(TILE_HELP[k], k) : ""}</div><div class="v ${vClass || ""}">${v}</div><div class="d ${cls}">${txt}</div></div>`;
  }

  function refSettings() {
    return Object.assign({}, REC, { bonds: state.bonds, intl_series: state.intl_series, who: state.who, gamma: state.gamma });
  }

  function update() {
    const r = ENGINE.run(state), ref = ENGINE.run(refSettings()), m = r.m, rm = ref.m;
    const pts = v => v.toFixed(v < 10 ? 1 : 0) + " pts";
    const over = m.boot_run_out > DATA.max_run_out + 0.0005;
    Help.hideIfDetached();
    $("tiles").innerHTML = [
      tile("Smooth-spending score", money(m.ce), delta(m.ce, rm.ce, money)),
      tile("Typical spending, yrs 1–10", money(m.typical_1_10), delta(m.typical_1_10, rm.typical_1_10, money)),
      tile("Typical spending, yrs 11–20", money(m.typical_11_20), delta(m.typical_11_20, rm.typical_11_20, money)),
      tile("Typical spending, yrs 21–30", money(m.typical_21_30), delta(m.typical_21_30, rm.typical_21_30, money)),
      tile("Ran out, real history", `${m.ran_out} of ${r.n}`, delta(m.ran_out, rm.ran_out, v => v.toFixed(0), false),
           m.ran_out ? "bad" : ""),
      tile("Ran out, reshuffled history", (m.boot_run_out * 100).toFixed(1) + "%",
           delta(m.boot_run_out * 100, rm.boot_run_out * 100, pts, false), over ? "bad" : ""),
      tile("Gave back ≥30% from best year", Math.round(m.give_back_share * 100) + "%",
           delta(m.give_back_share * 100, rm.give_back_share * 100, v => v.toFixed(0) + " pts", false)),
      tile("Median ending balance", "$" + m.median_final.toFixed(0), "per $100 started, real"),
    ].join("");
    $("warning").innerHTML = over ? `<div class="warn">Above the recommended plan's risk target: ${(m.boot_run_out * 100).toFixed(1)}% of
      5,000 reshuffled-history retirements run out of money (target: at most ${(DATA.max_run_out * 100).toFixed(0)}%).</div>` : "";
    drawPaths(r, ref); drawPain(r, ref); drawYears(r); drawRetiree();
  }

  // ---------- charts ----------
  function drawPaths(r, ref) {
    const cols = yrs.map((_, t) => column(r, t)), refCols = yrs.map((_, t) => column(ref, t));
    const lo = cols.map(c => percentile(c, 10)), med = cols.map(c => percentile(c, 50)), hi = cols.map(c => percentile(c, 90));
    const u = r.m.unluckiest, uy = r.starts[u];
    const tr = [
      { x: yrs, y: hi, line: { width: 0 }, hoverinfo: "skip", showlegend: false, type: "scatter", mode: "lines" },
      { x: yrs, y: lo, fill: "tonexty", fillcolor: C.band, line: { width: 0 }, name: "10th–90th percentile", type: "scatter",
        mode: "lines", customdata: lo.map((v, i) => [v, hi[i]]),
        hovertemplate: "Year %{x}: 10th–90th percentile $%{customdata[0]:.2f}–$%{customdata[1]:.2f}<extra></extra>" },
      { x: yrs, y: r.plan, name: "Plan", line: { color: C.muted, width: 1.4, dash: "dot" }, type: "scatter", mode: "lines",
        hovertemplate: "Year %{x}: plan $%{y:.2f}<extra></extra>" },
    ];
    if (r.params.ceiling > 0) tr.push({ x: yrs, y: r.plan.map(v => v * r.params.ceiling), name: "Cap", type: "scatter",
      mode: "lines", line: { color: C.muted, width: 1 }, hovertemplate: "Year %{x}: cap $%{y:.2f}<extra></extra>" });
    if (r.floor.some(v => v > 0)) tr.push({ x: yrs, y: r.floor, name: "Floor", type: "scatter", mode: "lines",
      line: { color: C.ink, width: 1, dash: "dash" }, hovertemplate: "Year %{x}: floor $%{y:.2f}<extra></extra>" });
    tr.push({ x: yrs, y: refCols.map(c => percentile(c, 50)), name: "Recommended plan: median", type: "scatter", mode: "lines",
      line: { color: C.ghost, width: 1.6, dash: "dash" }, hovertemplate: "Year %{x}: recommended median $%{y:.2f}<extra></extra>" });
    tr.push({ x: yrs, y: yrs.map((_, t) => r.reals(u, t)), name: `Unluckiest retiree (${uy} start)`, type: "scatter",
      mode: "lines", line: { color: C.bad, width: 1.6, dash: "longdash" },
      hovertemplate: `${uy} start, year %{x}: $%{y:.2f}<extra></extra>` });
    tr.push({ x: yrs, y: med, name: "Median retiree", type: "scatter", mode: "lines", line: { color: C.accent, width: 3 },
      hovertemplate: "Year %{x}: median $%{y:.2f}<extra></extra>" });
    const nar = window.innerWidth < 640;
    const lay = base("Spending over 30 years (real $ per $100 of starting portfolio)", nar ? 600 : 470,
      { legend: { orientation: "h", y: nar ? -0.17 : -0.26, yanchor: "top", x: 0 },
        margin: { l: nar ? 45 : 60, r: 12, t: 60, b: nar ? 190 : 110 } });
    lay.xaxis.title.text = "Year of retirement"; lay.xaxis.dtick = 5;
    lay.yaxis.title.text = nar ? "Real $ per $100" : "Real spending per $100 saved ($)"; lay.yaxis.rangemode = "tozero";
    Plotly.react("paths", tr, lay, CONFIG);
  }

  function drawPain(r, ref) {
    const rows = [["This plan", r], ["Recommended", ref]], labels = [], shares = [];
    rows.forEach(([name, res]) => [["below plan", res.m.levels], ["from best year", res.m.levels_best]].forEach(([meas, lv]) => {
      labels.push(`${name}: ${meas}`); shares.push(Engine.levelShares(lv));
    }));
    const tr = Engine.LEVELS.map(lv => {
      const vals = shares.map(s => s[lv] * 100);
      return { type: "bar", orientation: "h", y: labels, x: vals, name: LLAB[lv],
        marker: { color: LCOL[lv], line: { color: "white", width: 1.5 }, pattern: { shape: lv === "Ran out" ? "/" : "" } },
        text: vals.map(v => (v >= (window.innerWidth < 640 ? 14 : 7) ? v.toFixed(0) + "%" : "")), textposition: "inside",
        insidetextanchor: "middle", textangle: 0,
        textfont: { color: ["Severe", "Extreme", "Ran out"].includes(lv) ? "white" : C.ink },
        hovertemplate: "%{y}<br>" + LLAB[lv] + ": %{x:.0f}% of retirees<extra></extra>" };
    });
    const nar = window.innerWidth < 640;
    const lay = base("Deepest spending cut each retiree lived through", nar ? 470 : 350,
      { barmode: "stack", bargap: 0.35, legend: { orientation: "h", y: nar ? -0.12 : -0.32, yanchor: "top", x: 0, traceorder: "normal" },
        margin: { l: 20, r: 12, t: 60, b: nar ? 170 : 95 } });
    lay.xaxis.range = [0, 100]; lay.xaxis.ticksuffix = "%";
    lay.xaxis.title.text = nar ? "" : `Share of ${r.n} historical retirees`;
    lay.yaxis.autorange = "reversed"; lay.yaxis.showgrid = false; lay.yaxis.automargin = true;
    Plotly.react("pain", tr, lay, CONFIG);
  }

  function drawYears(r) {
    const lowest = [], early = [], endBal = [];
    for (let i = 0; i < r.n; i++) {
      let lo = Infinity, s = 0;
      for (let t = 0; t < 30; t++) { lo = Math.min(lo, r.reals(i, t)); if (t < 10) s += r.reals(i, t); }
      lowest.push(lo); early.push(s / 10); endBal.push(r.balance(i, 29));
    }
    const tr = [{ type: "bar", x: r.starts, y: lowest, marker: { color: C.accent }, name: "Lowest year",
      customdata: early.map((e, i) => [e, endBal[i]]),
      hovertemplate: "Retired %{x}<br>Lowest year: $%{y:.2f}<br>Average yrs 1–10: $%{customdata[0]:.2f}<br>Ending balance: $%{customdata[1]:.0f}<extra></extra>" }];
    const outYears = [], when = [];
    r.ranOut.forEach((ro, i) => { if (ro) { outYears.push(r.starts[i]); let t = 0; while (t < 30 && r.reals(i, t) >= 1e-9) t++; when.push(t + 1); } });
    if (outYears.length) tr.push({ type: "scatter", mode: "markers", x: outYears, y: outYears.map(() => 0.25), customdata: when,
      marker: { symbol: "x", size: 11, color: C.bad, line: { width: 2 } }, name: "Ran out of money",
      hovertemplate: "Retired %{x}: ran out in year %{customdata}<extra></extra>" });
    const n = outYears.length;
    const lay = base("Lowest yearly spending by start year" + (n ? ` · ${n} ran out (marked ×)` : " · none ran out"), 330,
      { showlegend: false });
    lay.xaxis.title.text = "Retirement start year"; lay.xaxis.dtick = 10;
    lay.yaxis.title.text = "Lowest yearly spending ($ per $100)"; lay.yaxis.rangemode = "tozero";
    if (r.floor.some(v => v > 0)) {
      const f = Math.min(...r.floor);
      lay.shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: f, y1: f, line: { color: C.ink, width: 1, dash: "dash" } }];
      lay.annotations = [{ xref: "paper", x: 0, y: f, yanchor: "bottom", xanchor: "left", text: "lowest floor",
        showarrow: false, font: { color: C.muted, size: 11 } }];
    }
    Plotly.react("years", tr, lay, CONFIG);
  }

  function drawRetiree() {
    const r = ENGINE.run(state), year = +$("year").value, k = r.starts.indexOf(year);
    const sp = yrs.map((_, t) => r.reals(k, t)), bal = yrs.map((_, t) => r.balance(k, t));
    const tr = [
      { type: "bar", x: yrs, y: sp, marker: { color: C.accent }, name: "Spending", hovertemplate: "Year %{x}: $%{y:.2f}<extra></extra>" },
      { type: "scatter", mode: "lines", x: yrs, y: r.plan, name: "Plan", line: { color: C.muted, dash: "dot" },
        hovertemplate: "Year %{x}: plan $%{y:.2f}<extra></extra>" },
    ];
    if (r.params.ceiling > 0) tr.push({ type: "scatter", mode: "lines", x: yrs, y: r.plan.map(v => v * r.params.ceiling),
      name: "Cap", line: { color: C.muted, width: 1 }, hovertemplate: "Year %{x}: cap $%{y:.2f}<extra></extra>" });
    if (r.floor.some(v => v > 0)) tr.push({ type: "scatter", mode: "lines", x: yrs, y: r.floor, name: "Floor",
      line: { color: C.ink, width: 1, dash: "dash" }, hovertemplate: "Year %{x}: floor $%{y:.2f}<extra></extra>" });
    tr.push({ type: "scatter", mode: "lines", x: yrs, y: bal, xaxis: "x2", yaxis: "y2", fill: "tozeroy",
      fillcolor: "rgba(134,182,239,0.35)", line: { color: C.accent, width: 2 }, name: "Portfolio",
      hovertemplate: "Year %{x}: $%{y:.0f}<extra></extra>" });
    const status = r.ranOut[k] ? "ran out of money" : `ended with $${bal[29].toFixed(0)}`;
    const lay = base(`One retiree: started in ${year} · ${status}`, 470, { showlegend: false });
    lay.yaxis.domain = [0.52, 1]; lay.yaxis.rangemode = "tozero";
    lay.xaxis.anchor = "y"; lay.xaxis.matches = "x2"; lay.xaxis.showticklabels = false;
    lay.xaxis2 = { anchor: "y2", showgrid: false, linecolor: C.grid, tickfont: { color: C.muted }, dtick: 5,
                   title: { text: "Year of retirement", font: { color: C.muted } } };
    lay.yaxis2 = { domain: [0, 0.4], anchor: "x2", gridcolor: C.grid, zeroline: false, rangemode: "tozero", tickfont: { color: C.muted } };
    lay.annotations = [
      { text: "Real spending ($ per $100 saved)", xref: "paper", yref: "paper", x: 0, y: 1.0, xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 12, color: C.muted } },
      { text: "Portfolio at year end (real $)", xref: "paper", yref: "paper", x: 0, y: 0.42, xanchor: "left", yanchor: "bottom", showarrow: false, font: { size: 12, color: C.muted } },
    ];
    Plotly.react("retiree", tr, lay, CONFIG);
  }

  // ---------- start ----------
  fetch("data.json").then(r => r.json()).then(d => {
    DATA = d; ENGINE = Engine.create(d); REC = Object.assign({}, d.recommended); state = Object.assign({}, REC);
    buildControls(); fromHash(); syncControls(); $("loading").remove(); update();
    let narrow = window.innerWidth < 640;
    window.addEventListener("resize", () => { const n = window.innerWidth < 640; if (n !== narrow) { narrow = n; update(); } });
  }).catch(e => { $("loading").textContent = "Could not load the data: " + e; });
})();
