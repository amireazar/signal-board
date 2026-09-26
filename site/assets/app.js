(() => {
  "use strict";
  const DATA_URL = "data/indicators.json";
  const REFRESH_MS = 5 * 60 * 1000;
  const LABEL = { bear: "Bearish", watch: "Watch", bull: "Bullish", na: "Not tracked" };
  const ROLE = { condition: "Condition", trigger: "Trigger", flow: "Flow" };
  const $ = (s) => document.querySelector(s);
  const state = { data: null, filter: "all", autoOnly: false, view: "level", chart: null, lastGenerated: null };

  try {
    const f = localStorage.getItem("ah-filter");
    if (f && (LABEL[f] || f === "all")) state.filter = f;
    state.autoOnly = localStorage.getItem("ah-auto") === "1";
  } catch (e) { /* storage unavailable */ }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  const st = (x) => (LABEL[x.status] ? x.status : "na");
  function fmtDate(s) {
    if (!s) return "";
    const d = new Date(s.length <= 10 ? s + "T12:00:00" : s);
    return isNaN(d) ? s : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
  function ago(iso) {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const h = Math.round(mins / 60);
    if (h < 48) return `${h} hr ago`;
    return fmtDate(iso);
  }

  // ------------------------------------------------------------ summary
  function tally(list) {
    const c = { bear: 0, watch: 0, bull: 0, na: 0 };
    list.forEach((x) => c[st(x)]++);
    return c;
  }
  function verdict(c) {
    const checked = c.bear + c.watch + c.bull;
    if (!checked) return "Not tracked yet";
    if (c.bear >= c.bull * 2 && c.bear > 0) return "Leaning bearish";
    if (c.bull >= c.bear * 2 && c.bull > 0) return "Leaning bullish";
    if (c.bull > c.bear) return "Slightly bullish";
    if (c.bear > c.bull) return "Slightly bearish";
    return "Mixed";
  }
  function headline(ind) {
    const cond = verdict(tally(ind.filter((x) => x.role === "condition")));
    const trig = verdict(tally(ind.filter((x) => x.role === "trigger")));
    const cb = /bearish/i.test(cond), tb = /bearish/i.test(trig);
    if (cb && !tb) return "The fuel for a correction is there. The spark isn't, yet.";
    if (cb && tb) return "Both the conditions and the triggers for a correction are lining up.";
    if (!cb && tb) return "Valuations aren't the problem. The triggers are flashing.";
    return "Few signs of an imminent correction.";
  }
  function renderSummary(ind) {
    const box = $("#summary-cards");
    box.replaceChildren();
    [["condition", "Conditions", "How far it could fall"], ["trigger", "Triggers", "What sets off a decline"], ["flow", "Flows", "Who is buying and selling"]].forEach(([role, title, sub]) => {
      const list = ind.filter((x) => x.role === role);
      const c = tally(list);
      const card = el("div", "card");
      card.appendChild(el("h2", null, `${title} · ${sub}`));
      card.appendChild(el("div", "verdict", verdict(c)));
      const bar = el("div", "bar");
      ["bear", "watch", "bull", "na"].forEach((k) => {
        if (!c[k]) return;
        const i = el("i", "st-" + k);
        i.style.width = (c[k] / list.length) * 100 + "%";
        bar.appendChild(i);
      });
      card.appendChild(bar);
      const counts = el("div", "counts");
      ["bear", "watch", "bull", "na"].forEach((k) => {
        const s = el("span");
        s.appendChild(el("i", "dot st-" + k));
        s.appendChild(document.createTextNode(`${c[k]} ${LABEL[k].toLowerCase()}`));
        counts.appendChild(s);
      });
      card.appendChild(counts);
      box.appendChild(card);
    });
    $("#headline").textContent = headline(ind);
    $("#n-ind").textContent = ind.length;
  }

  // ------------------------------------------------------------ changes
  function renderChanges(changes) {
    const panel = $("#changes-panel"), ul = $("#changes");
    if (!changes || !changes.length) { panel.hidden = true; return; }
    panel.hidden = false;
    ul.replaceChildren();
    changes.slice(0, 8).forEach((c) => {
      const li = el("li");
      const name = el("span");
      name.appendChild(el("strong", null, c.name));
      if (c.reading) name.appendChild(document.createTextNode(` · ${c.reading}`));
      li.appendChild(name);
      const arrow = el("span", "arrow");
      arrow.appendChild(el("span", "pill s-" + (LABEL[c.frm] ? c.frm : "na"), LABEL[c.frm] || "—"));
      arrow.appendChild(document.createTextNode("→"));
      arrow.appendChild(el("span", "pill s-" + (LABEL[c.to] ? c.to : "na"), LABEL[c.to] || "—"));
      li.appendChild(arrow);
      li.appendChild(el("span", "when", fmtDate(c.at)));
      ul.appendChild(li);
    });
    $("#changes-meta").textContent = `${changes.length} status change${changes.length === 1 ? "" : "s"} logged`;
  }

  // ------------------------------------------------------------ sparkline
  function spark(hist, status) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 110 34");
    svg.setAttribute("class", "spark");
    svg.setAttribute("aria-hidden", "true");
    if (!hist || hist.length < 2) return svg;
    const vals = hist.map((p) => p[1]);
    const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
    const x = (i) => 2 + (i / (vals.length - 1)) * 102;
    const y = (v) => 30 - ((v - min) / span) * 26;
    const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const color = getComputedStyle(document.documentElement).getPropertyValue("--" + (status === "na" ? "na" : status)).trim();
    const area = document.createElementNS(NS, "path");
    area.setAttribute("d", `${d} L${x(vals.length - 1)},32 L${x(0)},32 Z`);
    area.setAttribute("fill", color);
    area.setAttribute("opacity", "0.12");
    const line = document.createElementNS(NS, "path");
    line.setAttribute("d", d);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "1.6");
    const dot = document.createElementNS(NS, "circle");
    dot.setAttribute("cx", x(vals.length - 1));
    dot.setAttribute("cy", y(vals[vals.length - 1]));
    dot.setAttribute("r", "2.6");
    dot.setAttribute("fill", color);
    svg.append(area, line, dot);
    return svg;
  }

  // ------------------------------------------------------------ board
  function row(x) {
    const s = st(x);
    const r = el("div", "row");
    r.appendChild(el("div", "stripe st-" + s));
    const a = el("div");
    const role = el("div", "role", ROLE[x.role] || "");
    role.appendChild(el("span", "tag" + (x.mode === "auto" ? " live" : ""), x.mode === "auto" ? "Live" : "Analyst"));
    if (x.stale) role.appendChild(el("span", "tag stale", "Delayed"));
    a.appendChild(role);
    a.appendChild(el("div", "name", x.name));
    a.appendChild(el("div", "rule", x.rule));
    r.appendChild(a);
    const b = el("div", "c-read");
    if (x.reading) b.appendChild(el("div", "reading", x.reading));
    else b.appendChild(el("div", "reading none", x.hidden_value ? "Status only (licensed data)" : "—"));
    if (x.asOf) b.appendChild(el("div", "src", "As of " + fmtDate(x.asOf)));
    r.appendChild(b);
    const sp = el("div", "c-spark");
    if (x.history && x.history.length > 1) sp.appendChild(spark(x.history, s));
    r.appendChild(sp);
    const c = el("div", "c-note");
    if (x.note) c.appendChild(el("div", "note", x.note));
    if (x.source) c.appendChild(el("div", "src", x.source));
    r.appendChild(c);
    r.appendChild(el("span", "pill s-" + s, LABEL[s]));
    return r;
  }
  function renderBoard(ind) {
    const root = $("#groups");
    root.replaceChildren();
    const cats = [...new Set(ind.map((x) => x.cat))];
    let shown = 0;
    cats.forEach((cat) => {
      const all = ind.filter((x) => x.cat === cat);
      const list = all.filter((x) => (state.filter === "all" || st(x) === state.filter) && (!state.autoOnly || x.mode === "auto"));
      if (!list.length) return;
      shown += list.length;
      const g = el("section", "group");
      g.setAttribute("aria-label", cat);
      const h = el("div", "group-h");
      h.appendChild(el("h3", null, cat));
      const c = tally(all);
      h.appendChild(el("span", "mini", `${c.bear} bearish · ${c.watch} watch · ${c.bull} bullish · ${c.na} not tracked`));
      g.appendChild(h);
      list.forEach((x) => g.appendChild(row(x)));
      root.appendChild(g);
    });
    if (!shown) root.appendChild(el("p", "meta", "No indicators match this filter."));
  }

  // ------------------------------------------------------------ margin chart
  const VIEWS = {
    level: { key: "debit_bn", label: "Margin debt ($bn)", fmt: (v) => "$" + Math.round(v).toLocaleString() + "bn", caption: "Monthly debit balances, $ billions. Not adjusted for inflation or market size." },
    yoy: { key: "yoy", label: "Year-over-year change (%)", fmt: (v) => (v > 0 ? "+" : "") + v.toFixed(1) + "%", caption: "Growth above 30% has tended to come late in bull markets." },
    gdp: { key: "md_gdp", label: "Margin debt as % of GDP", fmt: (v) => v.toFixed(2) + "%", caption: "Adjusts borrowing for the size of the economy (GDP from BEA, quarterly)." },
    cash: { key: "cash_pct", label: "Free credit balances as % of margin debt", fmt: (v) => v.toFixed(1) + "%", caption: "Idle cash in brokerage accounts per dollar borrowed. A falling cushion means forced selling starts sooner." },
  };
  function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function renderChart() {
    const m = state.data && state.data.charts && state.data.charts.margin;
    const canvas = $("#margin-chart");
    if (!m || !window.Chart) {
      $("#margin-caption").textContent = m ? "Chart library is loading…" : "Margin data is unavailable right now.";
      return;
    }
    const v = VIEWS[state.view];
    const vals = m[v.key];
    const labels = m.labels.map((s) => { const [y, mo] = s.split("-"); return new Date(+y, +mo - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" }); });
    const ink = tok("--ink"), muted = tok("--muted"), rule = tok("--rule"), debt = tok("--debt"), soft = tok("--debt-soft"), surface = tok("--surface");
    if (state.chart) state.chart.destroy();
    Chart.defaults.font.family = tok("--sans");
    Chart.defaults.color = muted;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    state.chart = new Chart(canvas, {
      type: state.view === "yoy" ? "bar" : "line",
      data: { labels, datasets: [{
        label: v.label, data: vals,
        borderColor: debt, backgroundColor: state.view === "yoy" ? vals.map((x) => (x != null && x >= 0 ? debt : tok("--spx"))) : soft,
        fill: state.view !== "yoy", borderWidth: state.view === "yoy" ? 0 : 1.8, pointRadius: 0, tension: 0.2, spanGaps: false,
      }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: reduce ? false : { duration: 400 },
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { backgroundColor: surface, titleColor: ink, bodyColor: ink, borderColor: rule, borderWidth: 1, padding: 10,
          callbacks: { label: (c) => (c.raw == null ? " n/a" : " " + v.fmt(c.raw)) } } },
        scales: {
          x: { grid: { display: false }, border: { color: rule }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
          y: { grid: { color: rule }, border: { display: false }, ticks: { font: { family: tok("--mono") }, callback: (x) => v.fmt(x) } },
        },
      },
    });
    const lastIdx = vals.map((x, i) => (x == null ? -1 : i)).filter((i) => i >= 0).pop();
    $("#margin-caption").textContent = `${v.caption} Latest: ${v.fmt(vals[lastIdx])} (${labels[lastIdx]}).`;
    $("#margin-meta").textContent = `${labels[0]} – ${labels[labels.length - 1]} · FINRA`;
    $("#margin-title").textContent = `Margin debt since ${m.labels[0].slice(0, 4)}`;
  }

  // ------------------------------------------------------------ data
  function renderAll() {
    const d = state.data;
    if (!d) return;
    renderSummary(d.indicators);
    renderChanges(d.changes);
    renderBoard(d.indicators);
    renderChart();
    const upd = $("#updated");
    upd.replaceChildren();
    const ageH = (Date.now() - new Date(d.generated).getTime()) / 3600000;
    upd.appendChild(el("span", "pulse" + (ageH > 30 ? " stale" : "")));
    upd.appendChild(document.createTextNode(`Data updated ${ago(d.generated)}`));
    const live = d.indicators.filter((x) => x.mode === "auto").length;
    upd.appendChild(el("span", null, `· ${live} live indicators refresh automatically`));
    if (d.failures) upd.appendChild(el("span", null, `· ${d.failures} source${d.failures > 1 ? "s" : ""} delayed`));
  }
  async function load() {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const d = await res.json();
      if (d.generated !== state.lastGenerated) {
        state.data = d;
        state.lastGenerated = d.generated;
        renderAll();
      } else {
        renderAll(); // refresh the "updated … ago" text
      }
    } catch (e) {
      if (!state.data) $("#updated").textContent = "The data couldn't be loaded. Refresh the page to try again.";
    }
  }

  // ------------------------------------------------------------ controls
  document.querySelectorAll(".chip").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.f === state.filter));
    b.addEventListener("click", () => {
      state.filter = b.dataset.f;
      document.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      try { localStorage.setItem("ah-filter", state.filter); } catch (e) {}
      if (state.data) renderBoard(state.data.indicators);
    });
  });
  const auto = $("#auto-only");
  auto.checked = state.autoOnly;
  auto.addEventListener("change", () => {
    state.autoOnly = auto.checked;
    try { localStorage.setItem("ah-auto", auto.checked ? "1" : "0"); } catch (e) {}
    if (state.data) renderBoard(state.data.indicators);
  });
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      state.view = b.dataset.view;
      document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      renderChart();
    });
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  window.addEventListener("load", renderChart);
  $("#yr").textContent = new Date().getFullYear();

  load();
  setInterval(load, REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
