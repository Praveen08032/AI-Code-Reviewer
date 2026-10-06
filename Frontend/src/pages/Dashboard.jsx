import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { createGraph, ICON, countUp, sleep, prefersReducedMotion } from "@/lib/graph";
import { getHistory, errorMessage } from "@/lib/api";

const firstLine = (code = "") => (code.split("\n").find((l) => l.trim()) || "(empty)").trim();
const ago = (iso) => {
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  return d < 1 ? "Today" : d < 2 ? "Yesterday" : `${Math.floor(d)} days ago`;
};
const short = (s, n = 22) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export default function Dashboard() {
  const [subs, setSubs] = useState(null);
  const [error, setError] = useState("");
  const canvasRef = useRef(null);

  useEffect(() => {
    getHistory().then((d) => setSubs(d)).catch((e) => { setError(errorMessage(e)); setSubs([]); });
  }, []);

  const stats = useMemo(() => {
    if (!subs || !subs.length) return null;
    const n = subs.length, passed = subs.filter((s) => s.pass_status).length;
    const avg = (k) => subs.reduce((a, s) => a + (s[k] || 0), 0) / n;
    const py = subs.filter((s) => s.language === "python").length;
    const recent = [...subs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 3);
    const series = [...subs].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)).slice(-12);
    const first = series[0], last = series[series.length - 1];
    return { n, passed, pass: Math.round((passed / n) * 100), r: avg("readability_score"), e: avg("efficiency_score"), py, js: n - py, recent, series, first, last };
  }, [subs]);

  useEffect(() => {
    if (!stats || !canvasRef.current) return;
    const g = createGraph(canvasRef.current, 1400, 760, "drift");
    const card = (k, v, cls = "") => `<div class="card"><div><div style="min-width:0"><small class="k">${k}</small><div class="v ${cls}">${v}</div></div></div></div>`;
    const rec = stats.recent;
    const pos = [[40, 70, ""], [10, 300, ""], [150, 470, "far"]];
    rec.forEach((s, i) => {
      const [x, y, cls] = pos[i], lang = s.language === "python" ? "Python" : "JS";
      g.node(`r${i}`, x, y, 260, 96, card(`${ago(s.created_at)} · ${lang}`, short(firstLine(s.code)), "s"), cls, {
        k: "Recent review", t: firstLine(s.code), b: s.pass_status ? "Passed this review." : "Needs work: below the pass mark of 5 in at least one score.",
        s: [["Readability", `${s.readability_score ?? "–"} / 10`], ["Efficiency", `${s.efficiency_score ?? "–"} / 10`]], w: [i],
      });
    });
    g.node("agent", 500, 270, 420, 210, `<div class="card"><div>${ICON.bot(56)}<div class="ttl">CodeCheck AI<span>Your progress</span></div><span class="state">syncing</span></div></div>`, "big-agent",
      { k: "Agent", t: "CodeCheck AI · progress", b: "Every review you submit flows through the agent and updates the numbers on this dashboard.", s: [["Reviews", String(stats.n)], ["Passed", String(stats.passed)]], w: rec.map((_, i) => i).concat([3, 4, 5, 6, 7].map((x) => x - (3 - rec.length))) });
    g.node("k1", 1080, 40, 230, 110, card("Submissions", '<span data-c="n">0</span>'), "", { k: "Stat", t: `Submissions · ${stats.n}`, b: "Total pieces of code reviewed and saved to your database.", s: [["Python", String(stats.py)], ["JavaScript", String(stats.js)]], w: [rec.length] });
    g.node("k2", 1150, 210, 230, 110, card("Pass rate", '<span data-c="p">0</span>', "g"), "", { k: "Stat", t: `Pass rate · ${stats.pass}%`, b: "A review passes when readability and efficiency are both 5 or more.", s: [["Passed", String(stats.passed)], ["Needs work", String(stats.n - stats.passed)]], w: [rec.length + 1] });
    g.node("k3", 1130, 380, 230, 110, card("Avg readability", '<span data-c="r">0</span>'), "", { k: "Stat", t: `Average readability · ${stats.r.toFixed(1)}`, b: "How easy your code is to follow, out of 10.", s: [["First", `${stats.first.readability_score ?? "–"}`], ["Latest", `${stats.last.readability_score ?? "–"}`]], w: [rec.length + 2] });
    g.node("k4", 1040, 560, 230, 110, card("Avg efficiency", '<span data-c="e">0</span>'), "", { k: "Stat", t: `Average efficiency · ${stats.e.toFixed(1)}`, b: "How well your code uses time and memory, out of 10.", s: [["First", `${stats.first.efficiency_score ?? "–"}`], ["Latest", `${stats.last.efficiency_score ?? "–"}`]], w: [rec.length + 3] });
    g.node("k5", 560, 590, 290, 110, card("Languages", `Python ${stats.py} <small>· JS ${stats.js}</small>`), "far", { k: "Stat", t: "Languages", b: "How your practice is split between Python and JavaScript.", s: [["Python", String(stats.py)], ["JavaScript", String(stats.js)]], w: [rec.length + 4] });
    const inPts = [g.P("agent", "l", 0.3), g.P("agent", "l", 0.55), g.P("agent", "b", 0.2)];
    rec.forEach((_, i) => g.wire(g.P(`r${i}`, "r"), inPts[i], { label: "1 item", step: 0, flare: i < 2, white: i === 2 }));
    g.wire(g.P("agent", "r", 0.15), g.P("k1", "l"), { label: "Submissions", step: 1, flare: true });
    g.wire(g.P("agent", "r", 0.4), g.P("k2", "l"), { label: "Pass rate", step: 1, flare: true });
    g.wire(g.P("agent", "r", 0.65), g.P("k3", "l"), { label: "Readability", step: 1, white: true });
    g.wire(g.P("agent", "r", 0.9), g.P("k4", "l"), { label: "Efficiency", step: 1, flare: true });
    g.wire(g.P("agent", "b", 0.6), g.P("k5", "t"), { v: true, label: "Languages", step: 1, white: true });

    const host = canvasRef.current, el = (sel) => g.plane.querySelector(sel);
    const move = (e) => { const r = host.getBoundingClientRect(); g.plane.style.translate = `${((e.clientX - r.left) / r.width - 0.5) * -18}px ${((e.clientY - r.top) / r.height - 0.5) * -12}px`; };
    if (!prefersReducedMotion()) host.addEventListener("pointermove", move);
    let alive = true, first = true;
    (async () => {
      while (alive) {
        el("#agent .state").textContent = "syncing"; g.set("agent", "work"); g.pulse(0); await sleep(1300); if (!alive) break;
        g.unset("agent", "work"); g.set("agent", "on", "done"); el("#agent .state").textContent = "up to date";
        g.pulse(1); await sleep(1000); if (!alive) break;
        if (first) {
          countUp(el('[data-c="n"]'), stats.n); countUp(el('[data-c="p"]'), stats.pass, "%");
          countUp(el('[data-c="r"]'), stats.r, "<small> /10</small>", 1); countUp(el('[data-c="e"]'), stats.e, "<small> /10</small>", 1); first = false;
        }
        ["k1", "k2", "k3", "k4", "k5"].forEach((k, i) => g.timers.push(setTimeout(() => { g.set(k, "on"); g.timers.push(setTimeout(() => g.unset(k, "on"), 900)); }, i * 120)));
        await sleep(900); g.unset("agent", "on");
        if (prefersReducedMotion()) break;
        await sleep(4800);
      }
    })();
    return () => { alive = false; host.removeEventListener("pointermove", move); g.destroy(); };
  }, [stats]);

  const trend = useMemo(() => {
    if (!stats || stats.series.length < 2) return null;
    const s = stats.series, x = (i) => (i / (s.length - 1)) * 320, y = (v) => 90 - ((v ?? 0) / 10) * 90;
    const line = (k) => s.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d[k]).toFixed(1)}`).join(" ");
    return { r: line("readability_score"), e: line("efficiency_score"), pass: y(5) };
  }, [stats]);

  return (
    <section className="page" aria-labelledby="h-dash">
      <div className="ph">
        <h1 id="h-dash">Dashboard<span>/your progress</span></h1>
        {stats && <span className="tag green">{stats.n} reviews</span>}
        <span className="sp" />
        <Link className="btn btn-g" to="/submit?new=1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>New review</Link>
      </div>
      <div className="dash-area">
        <div className="canvas" ref={canvasRef} />
        {subs === null && <div className="empty-dash"><div className="loading">Loading your reviews…</div></div>}
        {subs && !stats && (
          <div className="empty-dash"><div>
            <b>{error ? "Could not load your reviews" : "No reviews yet"}</b>
            <p>{error || "Mark your first piece of code and your progress will appear here."}</p>
            <Link className="btn btn-g" to="/submit?new=1">Mark my code</Link>
          </div></div>
        )}
        {stats && <div className="tap" aria-hidden="true"><i />TAP ANY CARD FOR DETAILS</div>}
        {trend && (
          <div className="trend glass" aria-label={`Marks over your last ${stats.series.length} reviews`}>
            <h3>Marks over time<span><span style={{ color: "var(--green)" }}>●</span> Readability &nbsp;<span style={{ color: "#fff" }}>●</span> Efficiency</span></h3>
            <svg viewBox="0 0 320 90" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" x2="320" y1={trend.pass} y2={trend.pass} stroke="rgba(255,90,80,.6)" strokeDasharray="4 4" />
              <path className="ln" pathLength="1" stroke="#4ade5a" d={trend.r} />
              <path className="ln" pathLength="1" stroke="#eef1ed" style={{ animationDelay: ".7s" }} d={trend.e} />
            </svg>
          </div>
        )}
      </div>
    </section>
  );
}
