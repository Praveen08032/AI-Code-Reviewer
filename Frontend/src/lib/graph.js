// Animated node-graph engine (glowing wires, flowing particles, pulses) and hover/tap info cards.
const NS = "http://www.w3.org/2000/svg";
export const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const sleep = (ms) => new Promise((r) => setTimeout(r, prefersReducedMotion() ? 0 : ms));

/* ---------- info cards (one shared card for the whole app) ---------- */
let card, pinned = null;
function ensureCard() {
  if (card) return card;
  card = document.createElement("div");
  card.className = "icard"; card.id = "icard"; card.setAttribute("role", "tooltip");
  document.body.appendChild(card);
  document.addEventListener("click", () => unpin());
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") unpin(); });
  return card;
}
function unpin() { if (pinned) { pinned.classList.remove("pinned"); pinned.setAttribute("aria-expanded", "false"); } pinned = null; hideInfo(); }
export function hideInfo() {
  card?.classList.remove("show");
  document.querySelectorAll("svg.wires.dim").forEach((s) => s.classList.remove("dim"));
}
function showInfo(el, d, graph) {
  ensureCard();
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
  card.innerHTML = `<div class="k">${esc(d.k)}</div><h4>${esc(d.t)}</h4><p>${esc(d.b)}</p>` +
    (d.s ? `<div class="st">${d.s.map(([l, v]) => `<div>${esc(l)}<b>${esc(v)}</b></div>`).join("")}</div>` : "") +
    `<div class="hint">Tap the card again or press Esc to close</div>`;
  const r = el.getBoundingClientRect(), w = 300, h = card.offsetHeight || 190;
  let x = r.right + 16, y = r.top + r.height / 2 - h / 2;
  if (x + w > window.innerWidth - 12) x = r.left - w - 16;
  if (x < 80) { x = Math.min(window.innerWidth - w - 12, Math.max(80, r.left + r.width / 2 - w / 2)); y = r.bottom + 12; }
  card.style.left = x + "px";
  card.style.top = Math.max(12, Math.min(window.innerHeight - h - 12, y)) + "px";
  card.classList.add("show");
  if (graph && d.w) { graph.svg.classList.add("dim"); graph.wires.forEach((wr, i) => wr.g.classList.toggle("lit", d.w.includes(i))); }
}
export function attachInfo(el, getInfo, graph) {
  const d = () => (typeof getInfo === "function" ? getInfo() : getInfo);
  el.tabIndex = 0; el.setAttribute("role", "button");
  el.setAttribute("aria-label", `${d().t}. ${d().b}`);
  el.setAttribute("aria-expanded", "false");
  el.addEventListener("click", (e) => {
    e.stopPropagation();
    if (pinned === el) { unpin(); return; }
    if (pinned) { pinned.classList.remove("pinned"); pinned.setAttribute("aria-expanded", "false"); }
    pinned = el; el.classList.add("pinned"); el.setAttribute("aria-expanded", "true"); showInfo(el, d(), graph);
  });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.click(); } });
}

/* ---------- shared SVG defs (gradients and glow filters) ---------- */
function ensureDefs() {
  if (document.getElementById("cc-defs")) return;
  const holder = document.createElement("div");
  holder.innerHTML = `<svg id="cc-defs" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <linearGradient id="wg" x1="0" x2="1"><stop offset="0" stop-color="#4ade5a" stop-opacity=".25"/><stop offset=".5" stop-color="#4ade5a"/><stop offset="1" stop-color="#4ade5a" stop-opacity=".3"/></linearGradient>
    <linearGradient id="tailG" x1="0" x2="1"><stop offset="0" stop-color="#4ade5a" stop-opacity="0"/><stop offset="1" stop-color="#b6ffbf"/></linearGradient>
    <filter id="blur" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs></svg>`;
  document.body.appendChild(holder.firstElementChild);
}

/* ---------- graph ---------- */
export function createGraph(host, W, H, planeClass = "flat") {
  ensureDefs();
  const stage = document.createElement("div"); stage.className = "stage"; stage.style.width = W + "px"; stage.style.height = H + "px";
  const plane = document.createElement("div"); plane.className = "plane " + planeClass; stage.appendChild(plane);
  const svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "wires"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("aria-hidden", "true");
  plane.appendChild(svg); host.appendChild(stage);
  const g = { stage, plane, svg, wires: [], nodes: {}, timers: [] };

  g.fit = () => {
    const s = Math.min(host.clientWidth / W, host.clientHeight / H) * 0.98;
    stage.style.transform = `translate(${(host.clientWidth - W * s) / 2}px, ${(host.clientHeight - H * s) / 2}px) scale(${s})`;
  };
  g.node = (id, x, y, w, h, html, cls = "", info) => {
    const n = document.createElement("div");
    n.className = "node " + cls; n.id = id;
    Object.assign(n.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
    n.innerHTML = html + '<div class="busy"></div><svg class="ck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l5 5L20 7"/></svg>';
    plane.appendChild(n); g.nodes[id] = { el: n, x, y, w, h };
    if (info) attachInfo(n, info, g);
    return n;
  };
  g.P = (id, side, t = 0.5) => {
    const b = g.nodes[id];
    if (side === "r") return [b.x + b.w, b.y + b.h * t];
    if (side === "l") return [b.x, b.y + b.h * t];
    if (side === "b") return [b.x + b.w * t, b.y + b.h];
    return [b.x + b.w * t, b.y];
  };
  g.wire = (a, b, o = {}) => {
    const [x1, y1] = a, [x2, y2] = b;
    let d;
    if (o.v) { const dy = Math.max(70, Math.abs(y2 - y1) * 0.5); d = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`; }
    else { const dx = Math.max(90, Math.abs(x2 - x1) * 0.45); d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`; }
    const grp = document.createElementNS(NS, "g"); if (o.white) grp.setAttribute("class", "w-white");
    [["w-glow"], ["w-base"], ["w-dual", o.v ? "translate(6 0)" : "translate(0 5)"], ["w-stream" + (o.white ? " slow" : "")], ["w-tail"], ["w-pulse"]].forEach(([c, t]) => {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", d); p.setAttribute("class", c);
      if (t) p.setAttribute("transform", t);
      if (c === "w-pulse" || c === "w-tail") p.setAttribute("pathLength", "1");
      if (c.startsWith("w-stream")) { p.setAttribute("pathLength", "100"); p.style.animationDelay = (-Math.random() * 6).toFixed(2) + "s"; }
      grp.appendChild(p);
    });
    svg.appendChild(grp);
    const base = grp.querySelector(".w-base"), L = base.getTotalLength(), m = base.getPointAtLength(L * (o.at || 0.5));
    if (o.label) { const l = document.createElement("div"); l.className = "lbl"; l.textContent = o.label; l.style.left = m.x + "px"; l.style.top = m.y + "px"; plane.appendChild(l); }
    const fx = [];
    if (o.spikes) [[x1 + (o.v ? 0 : 6), y1 + (o.v ? 6 : 0)], [x2 - (o.v ? 0 : 6), y2 - (o.v ? 6 : 0)]].forEach(([x, y]) => {
      const s = document.createElement("div"); s.className = `spike ${o.v ? "d" : ""} ${o.white ? "w" : ""}`; s.style.left = x + "px"; s.style.top = y + "px"; plane.appendChild(s); fx.push(s);
    });
    if (o.flare) { const f = document.createElement("div"); f.className = "flare"; f.style.left = x2 + "px"; f.style.top = y2 + "px"; plane.insertBefore(f, svg); fx.push(f); }
    g.wires.push({ g: grp, step: o.step, fx });
  };
  g.pulse = (step) => g.wires.filter((w) => w.step === step).forEach((w, i) => {
    g.timers.push(setTimeout(() => {
      const p = w.g.querySelector(".w-pulse"), tl = w.g.querySelector(".w-tail");
      [p, tl].forEach((x) => { x.classList.remove("go"); void x.getBBox(); x.classList.add("go"); });
      w.fx.forEach((f, j) => g.timers.push(setTimeout(() => { f.classList.add("hot"); g.timers.push(setTimeout(() => f.classList.remove("hot"), 450)); }, 300 + j * 700)));
    }, prefersReducedMotion() ? 0 : i * 140));
  });
  g.set = (id, ...cls) => g.nodes[id]?.el.classList.add(...cls);
  g.unset = (id, ...cls) => g.nodes[id]?.el.classList.remove(...cls);
  const ro = new ResizeObserver(() => g.fit()); ro.observe(host);
  g.fit();
  g.destroy = () => { ro.disconnect(); g.timers.forEach(clearTimeout); hideInfo(); stage.remove(); };
  return g;
}

export const ICON = {
  code: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6"/></svg>',
  doc: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6v18h12V7zM14 3v4h4M9 13h6M9 17h4"/></svg>',
  spark: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></svg>',
  lib: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4h5v16H4zM10 4h4v16h-4zM15 5l4-1 2 15-4 1z"/></svg>',
  db: '<svg class="ico" style="width:30px;height:30px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/></svg>',
  bot: (size = 56) => `<svg class="ico" viewBox="0 0 40 40" style="width:${size}px;height:${size}px"><rect x="10" y="12" width="20" height="17" rx="6" fill="#e7eae6"/><rect x="14" y="17" width="3.5" height="5" rx="1.7" fill="#0e100e"/><rect x="22.5" y="17" width="3.5" height="5" rx="1.7" fill="#0e100e"/><rect x="17.5" y="6" width="5" height="5" rx="2.5" fill="#e7eae6"/><rect x="5" y="16" width="3" height="9" rx="1.5" fill="#e7eae6"/><rect x="32" y="16" width="3" height="9" rx="1.5" fill="#e7eae6"/><rect x="14" y="30" width="4" height="5" rx="2" fill="#e7eae6"/><rect x="22" y="30" width="4" height="5" rx="2" fill="#e7eae6"/></svg>`,
};

export function countUp(el, to, suffix = "", decimals = 0) {
  if (!el) return;
  if (prefersReducedMotion()) { el.innerHTML = Number(to).toFixed(decimals) + suffix; return; }
  const t0 = performance.now();
  const f = (t) => {
    const k = Math.max(0, Math.min(1, (t - t0) / 1100));
    el.innerHTML = (to * (1 - Math.pow(1 - k, 3))).toFixed(decimals) + suffix;
    if (k < 1) requestAnimationFrame(f);
  };
  requestAnimationFrame(f);
}
