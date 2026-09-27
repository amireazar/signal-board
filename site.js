(() => {
  "use strict";
  const ROOT = document.body.dataset.root || "./";
  const PAGE = document.body.dataset.page || "";
  const DATA_URL = ROOT + "data/indicators.json";
  const REFRESH_MS = 5 * 60 * 1000;
  const LABEL = { bear: "Downside risk", watch: "Borderline", bull: "Supportive", na: "Not tracked" };
  const SHORT = { bear: "Risk", watch: "Watch", bull: "Support", na: "—" };
  const ROLE = { condition: "Condition", trigger: "Trigger", flow: "Flow" };
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const state = { data: null, gen: null, charts: {} };

  // ------------------------------------------------------------------ utils
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  const st = (x) => (x && LABEL[x.status] ? x.status : "na");
  const tok = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
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
    return h < 48 ? `${h} hr ago` : fmtDate(iso);
  }
  const sign = (v, dp = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp));
  const ordinal = (n) => { n = Math.round(n); const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"); return n + s; };
  const byId = (id) => (state.data ? state.data.indicators.find((x) => x.id === id) : null);

  function spark(hist, colorVar, w = 110, h = 34) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("class", "spark");
    svg.setAttribute("aria-hidden", "true");
    if (!hist || hist.length < 2) return svg;
    const vals = hist.map((p) => (Array.isArray(p) ? p[1] : p)).filter((v) => v != null);
    const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
    const x = (i) => 1 + (i / (vals.length - 1)) * (w - 4);
    const y = (v) => h - 3 - ((v - min) / span) * (h - 7);
    const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const color = tok(colorVar) || tok("--accent");
    const area = document.createElementNS(NS, "path");
    area.setAttribute("d", `${d} L${x(vals.length - 1)},${h} L${x(0)},${h} Z`);
    area.setAttribute("fill", color);
    area.setAttribute("opacity", "0.12");
    const line = document.createElementNS(NS, "path");
    line.setAttribute("d", d);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "1.6");
    line.setAttribute("vector-effect", "non-scaling-stroke");
    const dot = document.createElementNS(NS, "circle");
    dot.setAttribute("cx", x(vals.length - 1));
    dot.setAttribute("cy", y(vals[vals.length - 1]));
    dot.setAttribute("r", "2.4");
    dot.setAttribute("fill", color);
    svg.append(area, line, dot);
    return svg;
  }
  const statusVar = (s) => "--" + (s === "na" ? "na" : s);

  function tally(list) {
    const c = { bear: 0, watch: 0, bull: 0, na: 0 };
    list.forEach((x) => c[st(x)]++);
    return c;
  }
  function verdict(c) {
    const checked = c.bear + c.watch + c.bull;
    if (!checked) return "Not tracked yet";
    if (c.bear >= c.bull * 2 && c.bear > 0) return "Leaning to downside risk";
    if (c.bull >= c.bear * 2 && c.bull > 0) return "Leaning supportive";
    if (c.bull > c.bear) return "Slightly supportive";
    if (c.bear > c.bull) return "Slightly toward risk";
    return "Mixed";
  }
  function regimeWord(ind) {
    const cb = /risk/i.test(verdict(tally(ind.filter((x) => x.role === "condition"))));
    const tb = /risk/i.test(verdict(tally(ind.filter((x) => x.role === "trigger"))));
    if (cb && tb) return { word: "Stressed", line: "Both conditions and triggers point to downside risk." };
    if (cb) return { word: "Fragile", line: "Conditions are stretched; triggers are not yet firing." };
    if (tb) return { word: "Unsettled", line: "Valuations are not the issue, but triggers are flashing." };
    return { word: "Steady", line: "Few signs of broad stress." };
  }
  function headline(ind) {
    const r = regimeWord(ind).word;
    return {
      Stressed: "Conditions and triggers for a correction are lining up.",
      Fragile: "The fuel for a correction is there. The spark isn't, yet.",
      Unsettled: "Valuations aren't the problem. The triggers are flashing.",
      Steady: "Few signs of an imminent correction.",
    }[r];
  }

  // ------------------------------------------------------------------ shared chrome
  function initChrome() {
    const btn = $(".menu-btn"), nav = $("#site-nav");
    if (btn && nav) btn.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", String(open));
    });
    $$("[data-year]").forEach((n) => (n.textContent = new Date().getFullYear()));
  }

  const TICKS = [
    ["t10", "US 10Y"], ["real", "10Y real"], ["curve", "2s10s"], ["fed", "Fed funds"],
    ["infl", "US inflation"], ["claims", "Claims"], ["mdyoy", "Margin debt YoY"], ["usd", "USD broad"], ["nfci", "NFCI"],
  ];
  function renderLivebar() {
    const bar = $("#livebar");
    if (!bar || !state.data) return;
    bar.replaceChildren();
    const ageH = (Date.now() - new Date(state.data.generated).getTime()) / 3600000;
    const live = el("span", "live-dot" + (ageH > 30 ? " stale" : ""));
    live.appendChild(el("i"));
    live.appendChild(document.createTextNode(ageH > 30 ? "Delayed" : "Updated " + ago(state.data.generated)));
    live.title = "Data updated " + ago(state.data.generated);
    bar.appendChild(live);
    TICKS.forEach(([id, label]) => {
      const x = byId(id);
      if (!x || !x.reading) return;
      const t = el("span", "tick");
      const s = st(x);
      const dot = el("i", "dot st-" + s);
      dot.title = LABEL[s];
      t.appendChild(dot);
      t.appendChild(document.createTextNode(label));
      t.appendChild(el("b", null, x.reading));
      bar.appendChild(t);
    });
    const im = state.data.intermarket;
    if (im && im.ratios) {
      ["gold_silver", "copper_gold", "brent_wti", "crack"].forEach((k) => {
        const r = im.ratios.find((x) => x.key === k);
        if (!r) return;
        const t = el("span", "tick");
        t.appendChild(document.createTextNode(r.name));
        t.appendChild(el("b", null, ordinal(r.pctile) + " pctile"));
        bar.appendChild(t);
      });
    }
  }

  // ------------------------------------------------------------------ home
  const PULSE_CATS = {
    "Valuation": "Valuation", "Leverage & positioning": "Leverage", "Rates & liquidity": "Rates",
    "Credit": "Credit", "Earnings & economy": "Economy", "Sentiment & technicals": "Sentiment",
    "Flows": "Flows", "Calendar & policy": "Policy",
  };
  function renderPulse() {
    const wrap = $("#pulse");
    if (!wrap || !state.data) return;
    const ind = state.data.indicators;
    const NS = "http://www.w3.org/2000/svg";
    $$("svg,.pulse-tip", wrap).forEach((n) => n.remove());
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "-50 -14 500 428");
    svg.setAttribute("role", "img");
    const c = tally(ind);
    svg.setAttribute("aria-label", `Macro Pulse: ${c.bear} indicators point to downside risk, ${c.watch} borderline, ${c.bull} supportive, ${c.na} not tracked.`);
    const cx = 200, cy = 200, r0 = 118;
    const cats = [...new Set(ind.map((x) => x.cat))];
    const gapDeg = 5, total = 360 - gapDeg * cats.length;
    const per = total / ind.length;
    const mk = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
    svg.appendChild(mk("circle", { cx, cy, r: r0 - 8, fill: "none", stroke: tok("--line-2"), "stroke-width": 1 }));
    const scan = mk("circle", { cx, cy, r: r0 - 20, fill: "none", stroke: tok("--accent"), "stroke-width": 1, "stroke-dasharray": "2 7", opacity: 0.55 });
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const an = mk("animateTransform", { attributeName: "transform", type: "rotate", from: `0 ${cx} ${cy}`, to: `360 ${cx} ${cy}`, dur: "60s", repeatCount: "indefinite" });
      scan.appendChild(an);
    }
    svg.appendChild(scan);
    const LEN = { bear: 62, watch: 42, bull: 26, na: 10 };
    let a = -90;
    const tip = el("div", "pulse-tip");
    tip.hidden = true;
    wrap.appendChild(tip);
    cats.forEach((cat) => {
      const items = ind.filter((x) => x.cat === cat);
      const start = a;
      items.forEach((x) => {
        const s = st(x);
        const ang = (a + per / 2) * Math.PI / 180;
        const r1 = r0, r2 = r0 + LEN[s];
        const x1 = cx + r1 * Math.cos(ang), y1 = cy + r1 * Math.sin(ang);
        const x2 = cx + r2 * Math.cos(ang), y2 = cy + r2 * Math.sin(ang);
        const line = mk("line", { x1, y1, x2, y2, stroke: tok(statusVar(s)), "stroke-width": Math.max(2.2, per * Math.PI / 180 * r0 * 0.5), "stroke-linecap": "round", opacity: s === "na" ? 0.55 : 0.95, tabindex: 0 });
        line.style.cursor = "pointer";
        const show = () => {
          tip.replaceChildren();
          tip.appendChild(el("b", null, x.name));
          tip.appendChild(document.createTextNode(`${x.reading || (x.hidden_value ? "Status only" : "—")} · ${LABEL[s]}`));
          const box = wrap.getBoundingClientRect(), sc = box.width / 500;
          tip.style.left = (x2 + 50) * sc + "px";
          tip.style.top = (y2 + 14) * sc + "px";
          tip.hidden = false;
          line.setAttribute("stroke-width", "5");
        };
        const hide = () => { tip.hidden = true; line.setAttribute("stroke-width", Math.max(2.2, per * Math.PI / 180 * r0 * 0.5)); };
        line.addEventListener("mouseenter", show);
        line.addEventListener("focus", show);
        line.addEventListener("mouseleave", hide);
        line.addEventListener("blur", hide);
        line.addEventListener("click", () => { location.href = ROOT + "monitor/#board"; });
        svg.appendChild(line);
        a += per;
      });
      const mid = ((start + a) / 2) * Math.PI / 180;
      const lr = 196;
      const lx = cx + lr * Math.cos(mid), ly = cy + lr * Math.sin(mid);
      const t = mk("text", { x: lx, y: ly + 3, "text-anchor": Math.abs(Math.cos(mid)) < 0.25 ? "middle" : Math.cos(mid) > 0 ? "start" : "end", fill: tok("--muted"), "font-size": 10.5, "font-family": tok("--mono"), "letter-spacing": "0.08em" });
      t.textContent = (PULSE_CATS[cat] || cat).toUpperCase();
      svg.appendChild(t);
      a += gapDeg;
    });
    wrap.insertBefore(svg, wrap.firstChild);
    const r = regimeWord(ind);
    $("#pulse-verdict").textContent = r.word;
    const checked = c.bear + c.watch + c.bull;
    $("#pulse-sub").textContent = `${c.bear} of ${checked} tracked indicators point to downside risk`;
  }

  const HOME_TILES = ["t10", "real", "infl", "oil", "mdyoy", "mdgdp", "claims", "nfci"];
  function tile(x) {
    const s = st(x);
    const t = el("div", "tile");
    const k = el("div", "k");
    k.appendChild(el("span", null, x.name));
    k.appendChild(el("span", "pill s-" + s, SHORT[s]));
    t.appendChild(k);
    t.appendChild(el("div", "v", x.reading || "—"));
    if (x.history && x.history.length > 1) t.appendChild(spark(x.history, statusVar(s), 200, 40));
    t.appendChild(el("div", "n", x.note || ""));
    if (x.asOf) t.appendChild(el("div", "when", "As of " + fmtDate(x.asOf)));
    return t;
  }
  function renderRegime(box) {
    if (!box) return;
    const ind = state.data.indicators;
    box.replaceChildren();
    [["condition", "Conditions", "How far it could fall"], ["trigger", "Triggers", "What sets off a decline"], ["flow", "Flows", "Who is buying and selling"]].forEach(([role, title, sub]) => {
      const list = ind.filter((x) => x.role === role);
      const c = tally(list);
      const card = el("div", "card");
      card.appendChild(el("span", "tagline", `${title} · ${sub}`));
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
  }
  function energyTile(e) {
    const t = el("div", "tile");
    const k = el("div", "k");
    k.appendChild(el("span", null, e.name));
    k.appendChild(el("span", "muted", e.unit));
    t.appendChild(k);
    t.appendChild(el("div", "v", (e.unit.startsWith("$") ? "$" : "") + e.value.toFixed(e.value < 20 ? 2 : 2)));
    t.appendChild(spark(e.history, "--accent", 200, 40));
    t.appendChild(el("div", "n", `${sign(e.chg_1m)}% 1 month · ${sign(e.chg_1y)}% 1 year`));
    t.appendChild(el("div", "when", "As of " + fmtDate(e.asOf)));
    return t;
  }
  function posRows(box, list, compact) {
    box.replaceChildren();
    const head = el("div", "pos-row head");
    ["Market", "Managed-money net, % of open interest", "3-yr pctile", compact ? "" : "2-yr trend"].forEach((h) => head.appendChild(el("span", null, h)));
    box.appendChild(head);
    const maxAbs = Math.max(20, ...list.map((p) => Math.abs(p.net_pct_oi)));
    list.forEach((p) => {
      const r = el("div", "pos-row");
      const n = el("div", "pos-name");
      n.appendChild(el("b", null, p.name));
      n.appendChild(el("span", null, `${p.group} · net ${p.net >= 0 ? "long" : "short"} ${Math.abs(p.net).toLocaleString()} contracts`));
      r.appendChild(n);
      const bar = el("div", "divbar");
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", `${p.name}: net ${p.net_pct_oi}% of open interest`);
      const i = el("i");
      const w = (Math.abs(p.net_pct_oi) / maxAbs) * 50;
      const crowd = p.pctile_3y >= 90 ? "--bear" : p.pctile_3y <= 10 ? "--bull" : "--accent";
      i.style.background = tok(crowd);
      i.style.width = w + "%";
      if (p.net_pct_oi >= 0) i.style.left = "50%"; else i.style.left = 50 - w + "%";
      bar.appendChild(i);
      r.appendChild(bar);
      const pc = el("div", "pctile", `${p.pctile_3y}th`);
      pc.appendChild(el("small", null, `${sign(p.net_pct_oi)}% of OI`));
      r.appendChild(pc);
      const sp = el("div", "c-spark");
      if (!compact) sp.appendChild(spark(p.history, crowd, 110, 30));
      r.appendChild(sp);
      box.appendChild(r);
    });
    if (!list.length) box.appendChild(el("p", "meta", "Positioning data is unavailable right now."));
  }
  function fmtRatio(r) {
    if (r.value == null) return r.z5 == null ? "—" : `z ${r.z5 > 0 ? "+" : ""}${r.z5.toFixed(2)}`;
    const v = r.value;
    if (r.unit === "%") return (v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%";
    if (Math.abs(v) >= 100) return Math.round(v).toLocaleString();
    return v.toFixed(2);
  }
  function ratioCard(r, onPick) {
    const c = el("button", "ratio");
    c.type = "button";
    c.setAttribute("aria-pressed", "false");
    c.dataset.key = r.key;
    const top = el("div", "top");
    top.appendChild(el("span", "grp", `${r.group} · ${r.freq}`));
    top.appendChild(el("span", "tagchip" + (r.license === "restricted" ? " lic" : ""), r.tag));
    c.appendChild(top);
    c.appendChild(el("h3", null, r.name));
    c.appendChild(el("div", "pair", r.pair + (r.unit === "×1000" ? " (×1000)" : "")));
    const val = el("div", "val");
    val.appendChild(el("b", null, fmtRatio(r)));
    if (r.chg_3m != null) {
      const pts = r.unit === "%";
      val.appendChild(el("span", "muted", `${r.chg_3m > 0 ? "▲" : r.chg_3m < 0 ? "▼" : "•"} ${Math.abs(r.chg_3m).toFixed(1)}${pts ? " pts" : "%"} 3m`));
    }
    c.appendChild(val);
    const g = el("div", "gauge");
    g.setAttribute("role", "img");
    g.setAttribute("aria-label", `${ordinal(r.pctile)} percentile of ${r.years} years`);
    g.appendChild(el("div", "track"));
    g.appendChild(el("div", "band"));
    const m = el("div", "mark" + (r.pctile >= 90 || r.pctile <= 10 ? " ext" : ""));
    m.style.left = Math.max(1, Math.min(99, r.pctile)) + "%";
    g.appendChild(m);
    c.appendChild(g);
    const foot = el("div", "foot");
    foot.appendChild(el("span", null, `${ordinal(r.pctile)} pctile · ${r.years}y`));
    foot.appendChild(el("span", null, r.z5 == null ? "" : `z ${r.z5 > 0 ? "+" : ""}${r.z5.toFixed(2)} vs 5y`));
    c.appendChild(foot);
    c.appendChild(el("p", "read", r.read));
    const f2 = el("div", "foot");
    f2.appendChild(el("span", null, "As of " + (r.freq === "Monthly" ? new Date(r.asOf + "T12:00:00").toLocaleDateString(undefined, { month: "short", year: "numeric" }) : fmtDate(r.asOf))));
    if (r.license === "restricted") f2.appendChild(el("span", null, "Level not shown (licensed input)"));
    c.appendChild(f2);
    c.addEventListener("click", () => onPick && onPick(r.key));
    return c;
  }
  function renderRead(prefix) {
    const im = state.data.intermarket;
    if (!im || !im.read) return;
    $(`#${prefix}-regime`).textContent = im.read.regime;
    $(`#${prefix}-line`).textContent = im.read.line;
    const ul = $(`#${prefix}-notes`);
    ul.replaceChildren();
    (im.read.notes || []).forEach((n) => ul.appendChild(el("li", null, n)));
  }

  function renderHome() {
    const d = state.data;
    renderPulse();
    const tiles = $("#home-tiles");
    tiles.replaceChildren();
    HOME_TILES.map(byId).filter(Boolean).forEach((x) => tiles.appendChild(tile(x)));
    renderRegime($("#home-regime"));
    const im = d.intermarket;
    const hr = $("#home-ratios");
    if (im && im.ratios && hr) {
      renderRead("hr");
      hr.replaceChildren();
      ["copper_gold", "gold_silver", "gold_oil", "crack", "spx_gold", "brent_wti"].forEach((k) => {
        const r = im.ratios.find((x) => x.key === k);
        if (r) hr.appendChild(ratioCard(r, () => { location.href = ROOT + "commodities/#" + k; }));
      });
    }
    const live = d.indicators.filter((x) => x.mode === "auto").length;
    const sl = $("#st-live"); if (sl) sl.textContent = `${live} live series`;
    const su = $("#st-updated"); if (su) su.textContent = `Updated ${ago(d.generated)}`;
  }

  // ------------------------------------------------------------------ monitor
  const mon = { filter: "all", autoOnly: false, view: "level" };
  try {
    const f = localStorage.getItem("ah-filter");
    if (f && (LABEL[f] || f === "all")) mon.filter = f;
    mon.autoOnly = localStorage.getItem("ah-auto") === "1";
  } catch (e) { /* storage unavailable */ }

  function boardRow(x) {
    const s = st(x);
    const r = el("div", "row");
    r.appendChild(el("div", "stripe st-" + s));
    const a = el("div");
    const role = el("div", "role", ROLE[x.role] || "");
    role.appendChild(el("span", "tag" + (x.mode === "auto" ? " live" : ""), x.mode === "auto" ? "Auto" : "Analyst"));
    if (x.stale) role.appendChild(el("span", "tag stale", "Delayed"));
    a.appendChild(role);
    a.appendChild(el("div", "name", x.name));
    a.appendChild(el("div", "rule", x.rule));
    r.appendChild(a);
    const b = el("div", "c-read");
    b.appendChild(x.reading ? el("div", "reading", x.reading) : el("div", "reading none", x.hidden_value ? "Status only (licensed data)" : "—"));
    if (x.asOf) b.appendChild(el("div", "src", "As of " + fmtDate(x.asOf)));
    r.appendChild(b);
    const sp = el("div", "c-spark");
    if (x.history && x.history.length > 1) sp.appendChild(spark(x.history, statusVar(s)));
    r.appendChild(sp);
    const c = el("div", "c-note");
    if (x.note) c.appendChild(el("div", "note", x.note));
    if (x.source) c.appendChild(el("div", "src", x.source));
    r.appendChild(c);
    r.appendChild(el("span", "pill s-" + s, LABEL[s]));
    return r;
  }
  function renderBoard() {
    const ind = state.data.indicators;
    const root = $("#groups");
    root.replaceChildren();
    let shown = 0;
    [...new Set(ind.map((x) => x.cat))].forEach((cat) => {
      const all = ind.filter((x) => x.cat === cat);
      const list = all.filter((x) => (mon.filter === "all" || st(x) === mon.filter) && (!mon.autoOnly || x.mode === "auto"));
      if (!list.length) return;
      shown += list.length;
      const g = el("section", "group");
      g.setAttribute("aria-label", cat);
      const h = el("div", "group-h");
      h.appendChild(el("h3", null, cat));
      const c = tally(all);
      h.appendChild(el("span", "mini", `${c.bear} risk · ${c.watch} borderline · ${c.bull} supportive · ${c.na} not tracked`));
      g.appendChild(h);
      list.forEach((x) => g.appendChild(boardRow(x)));
      root.appendChild(g);
    });
    if (!shown) root.appendChild(el("p", "meta", "No indicators match this filter."));
  }
  function renderChanges() {
    const changes = state.data.changes || [];
    const panel = $("#changes-panel"), ul = $("#changes");
    if (!changes.length) { panel.hidden = true; return; }
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
  const VIEWS = {
    level: { key: "debit_bn", fmt: (v) => "$" + Math.round(v).toLocaleString() + "bn", caption: "Monthly debit balances, $ billions, not adjusted for inflation or market size." },
    yoy: { key: "yoy", fmt: (v) => (v > 0 ? "+" : "") + v.toFixed(1) + "%", caption: "Growth above 30% has tended to come late in bull markets." },
    gdp: { key: "md_gdp", fmt: (v) => v.toFixed(2) + "%", caption: "Adjusts borrowing for the size of the economy (GDP from BEA, quarterly)." },
    cash: { key: "cash_pct", fmt: (v) => v.toFixed(1) + "%", caption: "Idle brokerage cash per dollar borrowed. A thinner cushion means forced selling starts sooner." },
  };
  function baseChartOptions(fmtY) {
    const ink = tok("--ink"), line = tok("--line"), surface = tok("--surface-2"), muted = tok("--muted");
    Chart.defaults.font.family = tok("--sans");
    Chart.defaults.color = muted;
    return {
      responsive: true, maintainAspectRatio: false,
      animation: matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 400 },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { backgroundColor: surface, titleColor: ink, bodyColor: ink, borderColor: tok("--line-2"), borderWidth: 1, padding: 10,
        callbacks: { label: (c) => (c.raw == null ? " n/a" : " " + fmtY(c.raw)) } } },
      scales: {
        x: { grid: { display: false }, border: { color: line }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 9 } },
        y: { grid: { color: line }, border: { display: false }, ticks: { font: { family: tok("--mono") }, callback: (v) => fmtY(v) } },
      },
    };
  }
  function renderMarginChart() {
    const m = state.data.charts && state.data.charts.margin;
    if (!m || !window.Chart) { $("#margin-caption").textContent = m ? "Chart is loading…" : "Margin data is unavailable right now."; return; }
    const v = VIEWS[mon.view], vals = m[v.key];
    const labels = m.labels.map((s) => { const [y, mo] = s.split("-"); return new Date(+y, +mo - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" }); });
    if (state.charts.margin) state.charts.margin.destroy();
    const accent = tok("--accent"), soft = tok("--accent-soft");
    state.charts.margin = new Chart($("#margin-chart"), {
      type: mon.view === "yoy" ? "bar" : "line",
      data: { labels, datasets: [{ data: vals, borderColor: accent,
        backgroundColor: mon.view === "yoy" ? vals.map((x) => (x != null && x >= 0 ? tok("--bear") : tok("--bull"))) : soft,
        fill: mon.view !== "yoy", borderWidth: mon.view === "yoy" ? 0 : 1.8, pointRadius: 0, tension: 0.2 }] },
      options: baseChartOptions(v.fmt),
    });
    const last = vals.map((x, i) => (x == null ? -1 : i)).filter((i) => i >= 0).pop();
    $("#margin-caption").textContent = `${v.caption} Latest: ${v.fmt(vals[last])} (${labels[last]}).`;
    $("#margin-meta").textContent = `${labels[0]} – ${labels[labels.length - 1]} · FINRA`;
    $("#margin-title").textContent = `Margin debt since ${m.labels[0].slice(0, 4)}`;
  }
  function renderMonitor() {
    const d = state.data;
    $("#headline").textContent = headline(d.indicators);
    renderRegime($("#summary-cards"));
    renderChanges();
    renderBoard();
    renderMarginChart();
    const live = d.indicators.filter((x) => x.mode === "auto").length;
    $("#updated").textContent = `Data updated ${ago(d.generated)} · ${live} live indicators refresh automatically` + (d.failures ? ` · ${d.failures} source${d.failures > 1 ? "s" : ""} delayed` : "");
  }
  function initMonitor() {
    $$(".chip").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.f === mon.filter));
      b.addEventListener("click", () => {
        mon.filter = b.dataset.f;
        $$(".chip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        try { localStorage.setItem("ah-filter", mon.filter); } catch (e) {}
        if (state.data) renderBoard();
      });
    });
    const auto = $("#auto-only");
    auto.checked = mon.autoOnly;
    auto.addEventListener("change", () => {
      mon.autoOnly = auto.checked;
      try { localStorage.setItem("ah-auto", auto.checked ? "1" : "0"); } catch (e) {}
      if (state.data) renderBoard();
    });
    $$("#margin .tabs button").forEach((b) => b.addEventListener("click", () => {
      mon.view = b.dataset.view;
      $$("#margin .tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      if (state.data) renderMarginChart();
    }));
    window.addEventListener("load", () => state.data && renderMarginChart());
  }

  // ------------------------------------------------------------------ commodities
  let ratioKey = (location.hash || "").replace("#", "") || "copper_gold";
  function renderRatioChart() {
    const im = state.data.intermarket;
    if (!im || !window.Chart) return;
    const r = im.ratios.find((x) => x.key === ratioKey) || im.ratios[0];
    if (!r) return;
    ratioKey = r.key;
    $$("#im-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.key === r.key)));
    $$("#im-ratios .ratio").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === r.key)));
    if (state.charts.ratio) state.charts.ratio.destroy();
    const isZ = r.history_kind === "z";
    const monthly = r.freq === "Monthly";
    const labels = r.history.map((p) => new Date(p[0] + "T12:00:00").toLocaleDateString(undefined, monthly ? { month: "short", year: "numeric" } : { month: "short", day: "numeric", year: "2-digit" }));
    const vals = r.history.map((p) => p[1]);
    const fmtY = isZ ? (v) => (v > 0 ? "+" : "") + v.toFixed(1) : r.unit === "%" ? (v) => v.toFixed(1) + "%" : (v) => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : v.toFixed(2));
    const hiLo = isZ ? [2, -2] : [r.p90, r.p10];
    const dash = { borderColor: tok("--faint"), borderWidth: 1, borderDash: [4, 4], pointRadius: 0, fill: false };
    state.charts.ratio = new Chart($("#im-chart"), {
      type: "line",
      data: { labels, datasets: [
        { data: vals, borderColor: tok("--accent"), backgroundColor: tok("--accent-soft"), fill: true, borderWidth: 1.8, pointRadius: 0, tension: 0.15 },
        Object.assign({ data: vals.map(() => hiLo[0]) }, dash),
        Object.assign({ data: vals.map(() => hiLo[1]) }, dash),
      ] },
      options: Object.assign(baseChartOptions(fmtY), { plugins: Object.assign(baseChartOptions(fmtY).plugins, { tooltip: Object.assign(baseChartOptions(fmtY).plugins.tooltip, { filter: (i) => i.datasetIndex === 0 }) }) }),
    });
    $("#im-chart-title").textContent = r.name;
    $("#im-chart-meta").textContent = `${r.pair} · ${r.freq.toLowerCase()} · as of ${fmtDate(r.asOf)}`;
    $("#im-chart-caption").textContent = isZ
      ? "Rolling 5-year z-score: how far the ratio sits from its own 5-year average, in standard deviations. Dashed lines mark ±2. Levels aren't shown because the ratio uses licensed index data."
      : `Dashed lines mark the 10th and 90th percentiles of the past ${r.years} years. ${r.read}`;
  }
  function renderHeat() {
    const im = state.data.intermarket;
    const t = $("#im-heat");
    if (!im || !im.correlations || !t) return;
    const SHORTN = { "WTI": "WTI", "Nat gas": "Gas", "10Y yield": "10Y", "Real yield": "Real", "Breakeven": "BE", "US dollar": "USD", "S&P 500": "SPX" };
    const { names, matrix } = im.correlations;
    t.replaceChildren();
    const thead = el("thead"), hr = el("tr");
    hr.appendChild(el("th"));
    names.forEach((n) => { const th = el("th", null, SHORTN[n] || n); th.title = n; hr.appendChild(th); });
    thead.appendChild(hr);
    t.appendChild(thead);
    const tb = el("tbody");
    const pos = tok("--bull"), neg = tok("--bear");
    names.forEach((a, i) => {
      const tr = el("tr");
      tr.appendChild(el("th", null, a));
      names.forEach((b, j) => {
        const v = matrix[i][j];
        const td = el("td", null, v == null ? "—" : i === j ? "·" : v.toFixed(2));
        if (v != null && i !== j) {
          const a2 = Math.min(1, Math.abs(v)) * 0.85;
          td.style.background = `color-mix(in srgb, ${v >= 0 ? pos : neg} ${Math.round(a2 * 100)}%, var(--surface-2))`;
        } else td.style.background = "var(--surface-2)";
        td.title = `${a} vs ${b}: ${v == null ? "n/a" : v.toFixed(2)}`;
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    const L = $("#im-links");
    L.replaceChildren();
    (im.links || []).forEach((l) => {
      const d = el("div", "link");
      d.appendChild(el("b", null, l.label));
      d.appendChild(el("span", "c", `${l.pair}: ${l.corr > 0 ? "+" : ""}${l.corr.toFixed(2)}`));
      d.appendChild(el("span", null, l.read));
      L.appendChild(d);
    });
    $("#im-corr-meta").textContent = `Correlation of daily changes, ${im.correlations.window}`;
  }
  function renderCommodities() {
    const im = state.data.intermarket;
    if (im && im.ratios) {
      renderRead("im");
      const grid = $("#im-ratios");
      grid.replaceChildren();
      const pick = (k) => { ratioKey = k; renderRatioChart(); $("#im-chart-panel").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); };
      im.ratios.forEach((r) => grid.appendChild(ratioCard(r, pick)));
      const tabs = $("#im-tabs");
      tabs.replaceChildren();
      im.ratios.forEach((r) => {
        const b = el("button", null, r.name);
        b.setAttribute("role", "tab");
        b.dataset.key = r.key;
        b.addEventListener("click", () => { ratioKey = r.key; renderRatioChart(); });
        tabs.appendChild(b);
      });
      renderRatioChart();
      renderHeat();
    } else {
      $("#im-ratios").replaceChildren(el("p", "meta", "Intermarket data is being prepared and will appear after the next update."));
    }
    const m = state.data.markets || {};
    posRows($("#pos-table"), m.positioning || [], false);
    const pa = (m.positioning || [])[0];
    if (pa) $("#pos-meta").textContent = `CFTC Disaggregated COT, futures only · positions as of ${fmtDate(pa.asOf)}`;
    $("#im-updated").textContent = `Data updated ${ago(state.data.generated)} · energy, rates and equity relationships daily; metals and grains monthly`;
    window.addEventListener("load", renderRatioChart, { once: true });
  }

  // ------------------------------------------------------------------ contact
  function initContact() {
    const form = $("#contact-form");
    if (!form) return;
    const q = new URLSearchParams(location.search).get("interest");
    if (q && $(`#f-interest option[value="${q}"]`)) $("#f-interest").value = q;
    const out = $("#f-msg-out"), btn = $("#f-submit");
    const id = (form.dataset.formspree || "").trim();
    if (!id) {
      btn.disabled = true;
      out.textContent = "The contact form is being connected. Please check back shortly.";
    }
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      out.className = "form-msg";
      const required = [["#f-name", "Enter your name."], ["#f-email", "Enter a valid work email."], ["#f-msg", "Add a short message."]];
      for (const [sel, msg] of required) {
        const f = $(sel);
        if (!f.value.trim() || (f.type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.value.trim()))) {
          out.textContent = msg; out.classList.add("err"); f.focus(); return;
        }
      }
      if (!$("#f-consent").checked) { out.textContent = "Please confirm the privacy consent to send your message."; out.classList.add("err"); return; }
      if (!id) return;
      btn.disabled = true;
      out.textContent = "Sending…";
      try {
        const res = await fetch(`https://formspree.io/f/${encodeURIComponent(id)}`, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error(String(res.status));
        form.reset();
        out.textContent = "Thanks. Your message was sent, and we'll reply within two business days.";
        out.classList.add("ok");
      } catch (e) {
        out.textContent = "Your message couldn't be sent. Check your connection and try again.";
        out.classList.add("err");
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ------------------------------------------------------------------ data loop
  function renderAll() {
    if (!state.data) return;
    renderLivebar();
    if (PAGE === "home") renderHome();
    if (PAGE === "monitor") renderMonitor();
    if (PAGE === "commodities") renderCommodities();
  }
  async function load() {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      const d = await res.json();
      state.data = d;
      state.gen = d.generated;
      renderAll();
    } catch (e) {
      const bar = $("#livebar");
      if (bar && !state.data) bar.innerHTML = '<span class="live-dot stale"><i></i>Offline</span><span class="tick">Live data is temporarily unavailable.</span>';
    }
  }

  initChrome();
  if (PAGE === "monitor") initMonitor();
  if (PAGE === "contact") initContact();
  if (["home", "monitor", "commodities"].includes(PAGE) || $("#livebar")) {
    load();
    setInterval(load, REFRESH_MS);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
})();
