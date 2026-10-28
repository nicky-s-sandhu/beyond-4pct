/* Withdrawal plan explorer: simulation engine.
 * A line-by-line port of src/bengen/vec.py (simulate, metrics) and app/model.py (run) from the
 * beyond-4pct repository. tests/test_web_engine.py checks that it matches the Python numbers.
 * Works in the browser (window.Engine) and in Node (module.exports).
 */
(function (root) {
  "use strict";

  const HORIZON = 30;
  const LEVELS = ["None", "Mild", "Moderate", "Severe", "Extreme", "Ran out"];

  // Blanchett (2014), Journal of Financial Planning 27(5), equation 1: real change from age to age + 1.
  function blanchettChange(age, expenditure) {
    return 0.00008 * age * age - 0.0125 * age - 0.00661 * Math.log(expenditure) + 0.546;
  }

  function toParams(s) {
    const cash = s.cash / 100;
    return {
      rate: s.rate / 100, stocks: s.stocks / 100, intl: s.intl / 100, band: s.band / 100,
      cutStep: s.cut_step / 100, raiseStep: s.raise_step / 100,
      floor: s.floor / 100, floorFlat: (s.floor_mode || "fixed") === "fixed", ceiling: +s.ceiling,
      drift: s.drift / 100, curve: s.curve === "blanchett" ? "blanchett" : "",
      startAge: 65, expenditure: 75000,
      cash: Math.min(cash, Math.max(0, 1 - s.stocks / 100)), bucket: cash > 0,
      threshold: s.threshold / 100, maxYears: Math.trunc(s.max_years), refillYears: Math.trunc(s.refill_years),
    };
  }

  function drifts(p, T) {
    const d = new Float64Array(T);
    for (let t = 1; t < T; t++) {
      d[t] = p.curve === "blanchett" ? blanchettChange(p.startAge + t - 1, p.expenditure) : p.drift;
    }
    return d;
  }

  function planPath(p, T) {          // planned real spending per $1 start
    const d = drifts(p, T), out = new Float64Array(T);
    let f = 1;
    for (let t = 0; t < T; t++) { f *= 1 + d[t]; out[t] = p.rate * f; }
    return out;
  }

  /* Series for one data choice. bonds: "intermediate" (1/2 bills + 1/2 10-year) or "10y". */
  function series(data, bonds, intlSeries) {
    const n = data.years.length;
    const B = new Float64Array(n);
    for (let i = 0; i < n; i++) B[i] = bonds === "intermediate" ? 0.5 * data.bills[i] + 0.5 * data.bonds10y[i] : data.bonds10y[i];
    return { US: data.stocks, INTL: data[intlSeries], B: B, C: data.bills, I: data.inflation, n: n };
  }

  /* Historical windows: every full T-year retirement. Returns index rows into the series. */
  function historyIndex(nYears, T) {
    const rows = [];
    for (let s = 0; s + T <= nYears; s++) { const r = new Uint8Array(T); for (let k = 0; k < T; k++) r[k] = s + k; rows.push(r); }
    return rows;
  }

  function decodeBoot(boot) {
    const bin = typeof atob === "function" ? atob(boot.idx_b64) : Buffer.from(boot.idx_b64, "base64").toString("binary");
    const rows = [];
    for (let i = 0; i < boot.n; i++) {
      const r = new Uint8Array(boot.T);
      for (let t = 0; t < boot.T; t++) r[t] = bin.charCodeAt(i * boot.T + t);
      rows.push(r);
    }
    return rows;
  }

  /* vec.simulate for every row of year indices. */
  function simulate(p, ser, rows, keep) {
    const n = rows.length, T = rows[0].length;
    const reals = keep ? new Float64Array(n * T) : null;
    const balances = keep ? new Float64Array(n * T) : null;
    const final = new Float64Array(n), depleted = new Uint8Array(n);
    const cash = p.cash > 0 ? p.cash : 0;
    const bondsW = Math.max(1 - p.stocks - cash, 0);
    const invS = p.stocks + bondsW > 0 ? p.stocks / (p.stocks + bondsW) : 1;
    const hiG = p.rate * (1 + p.band), loG = p.rate * (1 - p.band);
    const dr = drifts(p, T), planF = new Float64Array(T);
    { let f = 1; for (let t = 0; t < T; t++) { f *= 1 + dr[t]; planF[t] = f; } }
    const useBucketRule = p.bucket && cash > 0;
    const guard = p.cutStep > 0 || p.raiseStep > 0;
    for (let i = 0; i < n; i++) {
      const row = rows[i];
      let S = p.stocks, B = bondsW, C = cash, idx = 1, peak = 1, downRun = 0, price = 1, spend = p.rate;
      let dep = false;
      for (let t = 0; t < T; t++) {
        const y = row[t];
        const sr = p.intl > 0 ? (1 - p.intl) * ser.US[y] + p.intl * ser.INTL[y] : ser.US[y];
        if (t > 0) {
          const bal = S + B + C;
          const yp = row[t - 1];
          price = price * (1 + ser.I[yp]);
          spend = spend * (1 + ser.I[yp]) * (1 + dr[t]);
          if (guard) {
            const wr = bal > 0 ? spend / bal : Infinity;
            const alive = bal > 0;
            if (alive && wr > hiG) spend = spend * (1 - p.cutStep);
            if (alive && wr < loG) spend = spend * (1 + p.raiseStep);
          }
          const plan = p.rate * price * planF[t];
          if (p.floor > 0) spend = Math.max(spend, p.floor * (p.floorFlat ? p.rate * price : plan));
          if (p.ceiling > 0) spend = Math.min(spend, p.ceiling * plan);
        }
        S = S * (1 + sr);
        B = B * (1 + ser.B[y]);
        C = C * (1 + ser.C[y]);
        idx = idx * (1 + sr);
        peak = Math.max(peak, idx);
        const total = S + B + C;
        const take = Math.min(spend, total);
        if (take < spend - 1e-12) dep = true;
        let useBucket = false;
        if (useBucketRule) {
          const inDown = idx < peak * (1 - p.threshold);
          useBucket = inDown && downRun < p.maxYears;
          downRun = useBucket ? downRun + 1 : (inDown ? downRun : 0);
        }
        // bucket years: cash, then bonds, then stocks; no rebalancing
        const dC = Math.min(take, C), xC = take - dC;
        const dB = Math.min(xC, B), xB = xC - dB;
        const Sb = S - xB, Bb = B - dB, Cb = C - dC;
        // normal years: withdraw, refill/hold cash, rebalance the rest
        const totN = total - take;
        const tgt = cash * totN;
        let Cn;
        if (useBucketRule) {
          Cn = C > tgt ? tgt : (sr > 0 ? Math.min(tgt, C + tgt / p.refillYears) : C);
          Cn = Math.min(Cn, totN);
        } else Cn = tgt;
        const inv = totN - Cn;
        const Sn = inv * invS, Bn = inv * (1 - invS);
        if (useBucket) { S = Sb; B = Bb; C = Cb; } else { S = Sn; B = Bn; C = Cn; }
        if (keep) {
          reals[i * T + t] = take / price;
          balances[i * T + t] = (S + B + C) / (price * (1 + ser.I[y]));
        }
      }
      final[i] = (S + B + C) / (price * (1 + ser.I[row[T - 1]]));
      depleted[i] = dep ? 1 : 0;
    }
    return { n: n, T: T, reals: reals, balances: balances, final: final, depleted: depleted };
  }

  function median(arr) {
    const a = Array.from(arr).sort((x, y) => x - y), m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  function level(cut, ran) {
    if (ran) return "Ran out";
    if (cut >= 0.5 - 1e-9) return "Extreme";
    if (cut >= 0.3) return "Severe";
    if (cut >= 0.15) return "Moderate";
    if (cut >= 0.05) return "Mild";
    return "None";
  }

  function levelShares(levels) {
    const out = {};
    LEVELS.forEach(l => { out[l] = 0; });
    levels.forEach(l => { out[l] += 1 / levels.length; });
    return out;
  }

  /* vec.metrics plus the extras model.run adds. Spending in $ per $100 started. */
  function metrics(p, out, gamma, wRaw) {
    const n = out.n, T = out.T, R = out.reals, plan = planPath(p, T);
    const wSum = wRaw.reduce((a, b) => a + b, 0), w = wRaw.map(v => v / wSum);
    let acc = 0;
    const avg = (a, b) => { const v = new Float64Array(n); for (let i = 0; i < n; i++) { let s = 0; for (let t = a; t < b; t++) s += R[i * T + t]; v[i] = s / (b - a); } return v; };
    const levels = [], levelsBest = [];
    let ranOut = 0, giveBack = 0, unluckiest = 0, worst = Infinity;
    for (let i = 0; i < n; i++) {
      let cutPlan = 0, peakR = -Infinity, dropBest = -Infinity, u = 0, weighted = 0;
      const ran = out.depleted[i] === 1;
      for (let t = 0; t < T; t++) {
        const r = R[i * T + t];
        cutPlan = Math.max(cutPlan, Math.max(1 - r / plan[t], 0));
        const c = Math.max(r, 0.01);
        u += (gamma === 1 ? Math.log(c) : Math.pow(c, 1 - gamma)) * w[t];
        peakR = Math.max(peakR, r * 100);
        dropBest = Math.max(dropBest, 1 - (r * 100) / peakR);
        weighted += r * 100 * wRaw[t];
      }
      acc += u;
      if (ran) ranOut++;
      if (dropBest >= 0.3 || ran) giveBack++;
      levels.push(level(cutPlan, ran));
      levelsBest.push(level(dropBest, ran));
      if (weighted < worst) { worst = weighted; unluckiest = i; }
    }
    const meanU = acc / n;
    const ce = gamma === 1 ? Math.exp(meanU) : Math.pow(meanU, 1 / (1 - gamma));
    return {
      ce: ce * 100, ran_out: ranOut,
      typical_1_10: median(avg(0, 10)) * 100, typical_11_20: median(avg(10, 20)) * 100,
      typical_21_30: median(avg(20, 30)) * 100, median_final: median(out.final) * 100,
      give_back_share: giveBack / n, levels: levels, levels_best: levelsBest, unluckiest: unluckiest,
    };
  }

  function create(data) {
    const boot = decodeBoot(data.boot);
    const hist = historyIndex(data.years.length, HORIZON);
    const starts = hist.map(r => data.years[r[0]]);
    const serCache = {};
    const ser = (b, s) => (serCache[b + "|" + s] = serCache[b + "|" + s] || series(data, b, s));
    const cache = new Map();

    function run(settings) {
      const key = JSON.stringify(Object.keys(settings).sort().map(k => [k, settings[k]]));
      if (cache.has(key)) return cache.get(key);
      const p = toParams(settings);
      const sr = ser(settings.bonds, settings.intl_series);
      const out = simulate(p, sr, hist, true);
      const m = metrics(p, out, +settings.gamma, data.weights[settings.who]);
      const ob = simulate(p, sr, boot, false);
      m.boot_run_out = ob.depleted.reduce((a, b) => a + b, 0) / ob.n;
      const T = HORIZON, plan = planPath(p, T);
      const res = {
        settings: settings, params: p, starts: starts, n: out.n, T: T,
        reals: (i, t) => out.reals[i * T + t] * 100,
        balance: (i, t) => out.balances[i * T + t] * 100,
        plan: Array.from(plan, v => v * 100),
        floor: Array.from(plan, v => p.floor ? (p.floorFlat ? p.floor * p.rate * 100 : p.floor * v * 100) : 0),
        ranOut: Array.from(out.depleted, v => v === 1),
        final: Array.from(out.final, v => v * 100),
        m: m,
      };
      cache.set(key, res);
      if (cache.size > 40) cache.delete(cache.keys().next().value);
      return res;
    }
    return { run: run, starts: starts };
  }

  const api = { create: create, toParams: toParams, planPath: planPath, blanchettChange: blanchettChange,
                levelShares: levelShares, median: median, LEVELS: LEVELS, HORIZON: HORIZON };
  if (typeof module === "object" && module.exports) module.exports = api; else root.Engine = api;
})(typeof self !== "undefined" ? self : this);
