/* Withdrawal plan explorer: help text for every control and tile, and the help popover.
 * Hover the (?) icon for a moment to peek; click or tap it to pin the help open (close with ×, Esc or a click outside).
 */
(function (root) {
  "use strict";

  // title, body (HTML), optional "rec" line
  const HELP = {
    preset: ["Presets",
      "Load a whole set of settings at once, then adjust from there. <b>Recommended plan</b> is the plan from the study. " +
      "<b>Earlier plan</b> is the study's first recommendation, which turned out to run out of money too often outside real history. " +
      "<b>Bengen 4%</b> is the classic rule: fixed spending raised with inflation, 50/50 U.S. stocks and bonds. " +
      "<b>Previous 8% plan</b> is an aggressive early experiment."],
    reset: ["Reset", "Puts every setting back to the recommended plan."],
    share: ["Share these settings",
      "Copies a link that opens the explorer with your current settings, so you can send a scenario to someone or bookmark it."],

    rate: ["Starting withdrawal rate",
      "How much you spend in the first year, as a share of the portfolio. 6.5% means $65,000 from $1 million. " +
      "Later years follow the planned path and the yearly adjustments below. Higher starts mean more early spending but a higher " +
      "chance of running out and deeper cuts in bad markets.", "Recommended: 6.5%"],
    curve: ["Planned spending path",
      "How spending is planned to change each year after inflation, before any market-driven adjustments. " +
      "<b>Retirees' actual pattern</b> follows David Blanchett's 2014 research: real spending falls about 1% a year on average, " +
      "gently in the 60s, fastest around age 78 and leveling off near 90. <b>Fixed yearly change</b> uses the slider below instead.",
      "Recommended: retirees' actual pattern"],
    drift: ["Fixed real change per year",
      "Used only when the planned path is set to a fixed yearly change. −1% means planned spending falls 1% a year after " +
      "inflation, about 25% lower after 30 years. 0% is Bengen-style flat real spending."],
    floor: ["Spending floor",
      "The least you will ever spend, as a share of first-year spending, kept in today's dollars. 42% of $65,000 is $27,300. " +
      "A higher floor protects your lifestyle in bad markets, but the plan keeps paying it from a shrinking portfolio, so a floor " +
      "set too high makes running out more likely. 0 means no floor.", "Recommended: 42%"],
    ceiling: ["Spending cap",
      "The most you will ever spend, as a multiple of the planned path. 1.1 means never more than 10% above the plan. " +
      "Without a cap, raises in good markets can push spending up over time, against the declining plan; the cap keeps spending " +
      "on the planned pattern and leaves good-year money invested as a reserve. 0 means no cap.", "Recommended: 1.10×"],
    floor_mode: ["Floor measured against",
      "<b>First-year spending</b>: the floor is a fixed amount in today's dollars. <b>The declining plan</b>: the floor falls " +
      "along with the planned path, so it is lower in later years.", "Recommended: first-year spending"],

    band: ["No-change band",
      "Each year the plan compares planned spending with the current portfolio. While that withdrawal rate stays within this " +
      "distance of the starting rate, nothing changes. With a 6.5% start and a 22% band, a cut happens above 7.9% and a raise below " +
      "5.1%. A narrow band adjusts almost every year; a wide band adjusts rarely but by more when it does.",
      "Recommended: ±22%"],
    cut_step: ["Cut size",
      "How much spending is cut, after inflation, in a year when the withdrawal rate is above the band. Small cuts are easier to " +
      "live with but may come several years in a row.", "Recommended: 8.5%"],
    raise_step: ["Raise size",
      "The largest raise, after inflation, in a year when the withdrawal rate is below the band. Raises never take spending above " +
      "the cap.", "Recommended: up to 15%"],

    stocks: ["Stocks",
      "Share of the portfolio in stocks (U.S. plus international). The rest is in bonds, and in cash if you use the cash bucket. " +
      "The portfolio is rebalanced to this mix every year.", "Recommended: 80%"],
    intl: ["International share of stocks",
      "How much of the stock allocation is in developed markets outside the U.S. Diversifying abroad helped in the U.S.'s worst " +
      "stretches. The study capped it at 30%.", "Recommended: 30%"],

    cash: ["Cash bucket",
      "Optional. Sets aside this share of the portfolio in cash, taken from bonds. In a downturn, spending comes from cash and then " +
      "bonds instead of selling stocks. The study found it barely changes outcomes because annual rebalancing already buys stocks " +
      "when they fall; it is mainly for peace of mind. 0 turns it off.", "Recommended: off"],
    threshold: ["Downturn trigger",
      "The cash bucket is used when stocks are at least this far below their previous peak. Only matters when the cash bucket is on."],
    max_years: ["Max years funded from cash and bonds",
      "The longest run of downturn years paid from cash and bonds before selling stocks again. Only matters when the cash bucket is on."],
    refill_years: ["Refill over",
      "After a downturn, the bucket is topped back up in up years, a fraction at a time, over this many years. Only matters when " +
      "the cash bucket is on."],

    bonds: ["Bonds",
      "Which bond returns to use. <b>Intermediate</b> is half 3-month Treasury bills and half 10-year Treasuries, a stand-in for the " +
      "intermediate government bonds in Bengen's study. <b>10-year Treasury</b> is a longer, more volatile bond."],
    intl_series: ["International data",
      "<b>Base</b> skips the war years when some foreign markets closed. <b>Pessimistic</b> fills those gaps with heavy losses, " +
      "a stress test for the international allocation."],
    who: ["Score weights years by",
      "Later years count less in the smooth-spending score because you may not be alive to spend them. <b>Couple</b> weights each " +
      "year by the chance at least one of a 65-year-old couple is alive; <b>single</b> by the chance one person is; <b>equal</b> " +
      "counts every year the same. Only the score changes, not the simulation."],
    gamma: ["Risk aversion",
      "How strongly the smooth-spending score penalizes lean years. At 3, a year at half the usual spending hurts much more than " +
      "a year at 1.5 times it helps. Higher values favor steady, safe plans; lower values favor plans with higher average spending. " +
      "Only the score changes, not the simulation.", "Recommended: 3"],
    year: ["Explore one retiree",
      "Pick a retirement start year to see that retiree's spending each year and their portfolio balance. 1929 and the mid-1960s " +
      "are the hardest starts in U.S. history."],

    t_score: ["Smooth-spending score",
      "One number for how good the spending was, per $100 saved: the steady yearly amount a retiree would value as much as the " +
      "plan's ups and downs. It rewards high, steady and early spending and heavily penalizes lean years and running out. Compare " +
      "plans with it; it is not a spending figure."],
    t_typ1: ["Typical spending, years 1–10",
      "The middle retiree's average yearly spending in the first decade, per $100 saved, in today's dollars, across the 69 real retirements."],
    t_typ2: ["Typical spending, years 11–20", "As above, for the second decade."],
    t_typ3: ["Typical spending, years 21–30", "As above, for the third decade."],
    t_hist: ["Ran out, real history",
      "How many of the 69 historical retirements (starting each year from 1928 to 1996) ran out of money within 30 years."],
    t_boot: ["Ran out, reshuffled history",
      "Share of 5,000 extra retirements, built by stitching together random runs of real years, that ran out within 30 years. " +
      "History only happened once; reshuffling tests how a plan does on sequences it was not tuned to. The recommended plan targets " +
      "at most 2%."],
    t_give: ["Gave back 30% or more from best year",
      "Share of retirees whose spending at some point fell 30% or more below their best year so far, including planned declines. " +
      "A rough measure of how often a big step down was felt."],
    t_end: ["Median ending balance",
      "What the middle retiree had left after 30 years, per $100 started, in today's dollars. A reserve for living longer, for " +
      "late-life care or for heirs."],
  };

  let pop = null, pinned = false, timer = null, owner = null;

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div");
    pop.className = "help-pop";
    pop.setAttribute("role", "dialog");
    pop.hidden = true;
    document.body.appendChild(pop);
    return pop;
  }

  function place(btn) {
    const r = btn.getBoundingClientRect(), p = ensurePop();
    const vw = document.documentElement.clientWidth, vh = window.innerHeight;
    p.style.maxWidth = Math.min(340, vw - 24) + "px";
    p.style.left = "0px"; p.style.top = "0px";
    const w = p.offsetWidth, h = p.offsetHeight;
    let left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), vw - w - 12);
    let top = r.bottom + 8;
    if (top + h > vh - 8 && r.top - h - 8 > 8) top = r.top - h - 8;
    p.style.left = left + "px"; p.style.top = Math.max(8, top) + "px";
  }

  function show(btn, pin) {
    const key = btn.dataset.help, h = HELP[key];
    if (!h) return;
    const p = ensurePop();
    p.innerHTML = `<div class="help-head"><b>${h[0]}</b>` +
      (pin ? `<button type="button" class="help-close" aria-label="Close help">×</button>` : "") + `</div>` +
      `<div>${h[1]}</div>` + (h[2] ? `<div class="help-rec">${h[2]}</div>` : "") +
      (pin ? `<a class="help-more" href="help.html">How to use the explorer</a>` : "");
    p.classList.toggle("pinned", !!pin);
    p.hidden = false;
    pinned = !!pin; owner = btn;
    document.querySelectorAll(".help-btn[aria-expanded=true]").forEach(b => b.setAttribute("aria-expanded", "false"));
    btn.setAttribute("aria-expanded", "true");
    place(btn);
    if (pin) { const c = p.querySelector(".help-close"); c.addEventListener("click", hide); c.focus({ preventScroll: true }); }
  }

  function hide() {
    if (!pop) return;
    pop.hidden = true;
    const o = owner;
    pinned = false; owner = null;
    if (o) { o.setAttribute("aria-expanded", "false"); }
  }

  function icon(key, label) {
    return `<button type="button" class="help-btn" data-help="${key}" aria-label="Help: ${label || (HELP[key] || [key])[0]}" ` +
      `aria-expanded="false" aria-haspopup="dialog">?</button>`;
  }

  // One set of listeners for every (?) icon, present or added later.
  document.addEventListener("pointerover", e => {
    const btn = e.target.closest && e.target.closest(".help-btn");
    if (!btn || e.pointerType !== "mouse" || pinned) return;
    clearTimeout(timer);
    timer = setTimeout(() => show(btn, false), 450);          // a deliberate (long) hover, not a pass-over
  });
  document.addEventListener("pointerout", e => {
    const btn = e.target.closest && e.target.closest(".help-btn");
    if (!btn || e.pointerType !== "mouse") return;
    clearTimeout(timer);
    if (!pinned && owner === btn) hide();
  });
  document.addEventListener("click", e => {
    const btn = e.target.closest(".help-btn");
    if (btn) {
      e.preventDefault(); e.stopPropagation(); clearTimeout(timer);
      if (pinned && owner === btn) hide(); else show(btn, true);
      return;
    }
    if (pinned && pop && !pop.contains(e.target)) hide();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && pop && !pop.hidden) { const o = owner; hide(); if (o) o.focus(); }
  });
  window.addEventListener("resize", () => { if (owner && pop && !pop.hidden) place(owner); });
  window.addEventListener("scroll", () => { if (owner && pop && !pop.hidden) { if (pinned) place(owner); else hide(); } }, true);

  // Tiles are redrawn on every change: drop a popover whose icon is about to be replaced.
  function hideIfDetached() { if (owner && owner.closest("#tiles")) hide(); }

  root.Help = { HELP: HELP, icon: icon, hide: hide, hideIfDetached: hideIfDetached };
})(typeof self !== "undefined" ? self : this);
