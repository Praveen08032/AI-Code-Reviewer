import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { createGraph, ICON, countUp, sleep } from "@/lib/graph";
import { getSamples, submitCode, errorMessage, titleCase, fileName } from "@/lib/api";
import { defineTheme } from "@/lib/editorTheme";

const STARTER = {
  python: "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(len(nums)):\n            if i != j and nums[i] + nums[j] == target:\n                return [i, j]\n    return []\n\nprint(two_sum([2, 7, 11, 15], 9))",
  javascript: "function reverseString(s) {\n  let out = \"\";\n  for (let i = 0; i < s.length; i++) {\n    out = s[i] + out;\n  }\n  return out;\n}",
};


export default function SubmitCode() {
  const [params] = useSearchParams();
  const [samples, setSamples] = useState([]);
  const [lang, setLang] = useState(params.get("lang") || "python");
  const [question, setQuestion] = useState(params.get("q") || "two sum");
  const [code, setCode] = useState(params.get("q") ? "" : STARTER[params.get("lang") || "python"]);
  const [tab, setTab] = useState("editor");
  const [status, setStatus] = useState({ kind: "", text: "Ready · press Run review", time: "" });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const canvasRef = useRef(null), graphRef = useRef(null), scoreRefs = useRef([]);
  const editorRef = useRef(null), monacoRef = useRef(null), decoRef = useRef([]);

  useEffect(() => { getSamples().then(setSamples).catch(() => {}); }, []);
  useEffect(() => { if (params.get("new")) { setCode(STARTER[lang]); setResult(null); setTab("editor"); } }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const questions = useMemo(() => samples.filter((s) => s.language === lang).map((s) => s.question_title), [samples, lang]);
  useEffect(() => { if (questions.length && !questions.includes(question.toLowerCase())) setQuestion(questions[0]); }, [questions]); // eslint-disable-line react-hooks/exhaustive-deps
  const file = fileName(question, lang);

  // build the review workflow once
  useEffect(() => {
    const g = createGraph(canvasRef.current, 1000, 620, "flat");
    g.node("trig", 60, 230, 130, 130, `<div class="card"><div class="c">${ICON.code}</div></div><div class="cap">When code<br>is submitted</div>`, "",
      { k: "Trigger", t: "When code is submitted", b: "Starts when you press Run review. Sends your code, language and question to the agent.", w: [0] });
    g.node("agent", 360, 235, 240, 120, `<div class="card"><div>${ICON.bot(40)}<div class="ttl">CodeCheck AI<span>Review Agent</span></div></div></div>`, "",
      { k: "Agent", t: "Review Agent", b: "Sends your code to Google Gemini with a structured prompt, then parses the bugs, scores and improved version.", s: [["Model", "Gemini"], ["Typical time", "5–10 s"]], w: [0, 1, 2, 3] });
    g.node("report", 780, 235, 130, 120, `<div class="card"><div class="c">${ICON.doc}</div></div><div class="cap">Review report<small>5 outputs</small></div>`, "",
      { k: "Output", t: "Review report", b: "Bugs, suggestions, readability and efficiency scores, similarity to the model answer and an improved version.", w: [1, 4] });
    g.node("model", 270, 470, 110, 100, `<div class="card"><div class="c">${ICON.spark}</div></div><div class="cap">Gemini<small>chat model</small></div>`, "",
      { k: "Chat model", t: "Google Gemini", b: "The AI model that reads and reviews your code. The free plan allows about 20 reviews a day.", s: [["Model", "Flash-Lite"], ["Free limit", "≈20 / day"]], w: [2] });
    g.node("mem", 470, 490, 110, 100, `<div class="card"><div class="c">${ICON.lib}</div></div><div class="cap">Model answers<small>memory</small></div>`, "",
      { k: "Memory", t: "Model answers", b: "The ideal solution for the chosen question, used to calculate the similarity score.", s: [["Method", "difflib"], ["Similar at", "70%+"]], w: [3] });
    g.node("db", 760, 470, 170, 100, `<div class="card"><div style="gap:10px;padding:0 16px">${ICON.db}<div class="ttl" style="font-size:16px">PostgreSQL<span style="font-size:13px">saved</span></div></div></div>`, "",
      { k: "Storage", t: "PostgreSQL · Neon", b: "Every review is saved here and appears on your dashboard and in history.", w: [4] });
    g.wire(g.P("trig", "r"), g.P("agent", "l"), { label: "1 item", step: 0, spikes: true });
    g.wire(g.P("agent", "r"), g.P("report", "l"), { label: "1 item", step: 2, spikes: true });
    g.wire(g.P("agent", "b", 0.25), g.P("model", "t"), { v: true, label: "Chat model", at: 0.25, step: 1, spikes: true });
    g.wire(g.P("agent", "b", 0.55), g.P("mem", "t"), { v: true, white: true, label: "Memory", at: 0.25, step: 1, spikes: true });
    g.wire(g.P("report", "b"), g.P("db", "t"), { v: true, label: "Save", step: 3, spikes: true });
    graphRef.current = g;
    return () => g.destroy();
  }, []);

  function resetGraph() {
    const g = graphRef.current; if (!g) return;
    Object.keys(g.nodes).forEach((id) => g.unset(id, "on", "done", "work", "fail"));
    scoreRefs.current.forEach((el) => el && (el.textContent = "–"));
    decoRef.current = editorRef.current?.deltaDecorations(decoRef.current, []) || [];
  }

  // highlight lines mentioned by the AI ("line 3", "lines 2-3")
  function markLines(items) {
    const ed = editorRef.current, monaco = monacoRef.current; if (!ed || !monaco) return;
    const ranges = [];
    items.forEach((t) => { const m = t.match(/lines?\s+(\d+)(?:\s*(?:-|–|to|and)\s*(\d+))?/i); if (m) ranges.push([+m[1], +(m[2] || m[1])]); });
    decoRef.current = ed.deltaDecorations(decoRef.current, ranges.map(([a, b]) => ({ range: new monaco.Range(a, 1, b, 1), options: { isWholeLine: true, className: "cc-bad-line", glyphMarginClassName: "cc-bad-glyph" } })));
  }

  async function run() {
    if (running) return;
    if (!code.trim()) { setStatus({ kind: "err", text: "Write or paste some code first", time: "" }); return; }
    const g = graphRef.current;
    setRunning(true); setTab("editor"); resetGraph(); setResult(null);
    const t0 = performance.now();
    const request = submitCode({ language: lang, question_title: question, code });
    setStatus({ kind: "live", text: `Reading ${file}`, time: "" });
    g.set("trig", "on", "done"); g.pulse(0); await sleep(1100);
    g.unset("trig", "on"); g.set("agent", "on", "work"); setStatus({ kind: "live", text: "Agent reviewing with Gemini…", time: "" });
    g.pulse(1); await sleep(1000); g.set("model", "on"); g.set("mem", "on");
    let data;
    try { data = await request; }
    catch (err) {
      g.unset("agent", "work", "on"); g.unset("model", "on"); g.unset("mem", "on"); g.set("agent", "fail");
      setStatus({ kind: "err", text: "Review failed", time: "", msg: errorMessage(err) }); setRunning(false); return;
    }
    g.unset("model", "on"); g.unset("mem", "on"); g.unset("agent", "work", "on"); g.set("agent", "done");
    g.pulse(2); await sleep(1000); g.set("report", "on", "done");
    const [s1, s2, s3] = scoreRefs.current;
    countUp(s1, data.readability_score ?? 0, "/10"); countUp(s2, data.efficiency_score ?? 0, "/10");
    if (data.similarity_score != null) countUp(s3, data.similarity_score, "%", 0); else s3.textContent = "n/a";
    markLines([...(data.errors || []), ...(data.suggestions || [])]);
    g.pulse(3); await sleep(1000); g.unset("report", "on"); g.set("db", "on", "done"); await sleep(400); g.unset("db", "on");
    setStatus({ kind: "ok", text: "Completed · saved to dashboard", time: ((performance.now() - t0) / 1000).toFixed(1) + "s" });
    setResult(data); setRunning(false);
  }

  const copy = (txt) => { navigator.clipboard?.writeText(txt).catch(() => {}); flash("Improved version copied"); };
  const [toast, setToast] = useState("");
  const flash = (t) => { setToast(t); setTimeout(() => setToast(""), 1800); };

  return (
    <section className="page" aria-labelledby="h-mark">
      <style>{`.cc-bad-line { background: rgba(255,90,80,.12); } .cc-bad-glyph { background: #ff8b80; width: 3px !important; margin-left: 4px; }`}</style>
      <div className="ph">
        <h1 id="h-mark">Code Review Agent<span>/{file}</span></h1>
        {result && <span className={`tag ${result.pass_status ? "green" : "red"}`}>{result.pass_status ? "Passed" : "Needs work"}</span>}
        <span className="sp" />
        <button className="btn btn-g" onClick={run} disabled={running}>
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>{running ? "Reviewing…" : "Run review"}
        </button>
      </div>
      <div className="tabs" role="tablist" aria-label="Review views">
        <button role="tab" aria-selected={tab === "editor"} onClick={() => setTab("editor")}>Editor</button>
        <button role="tab" aria-selected={tab === "results"} onClick={() => setTab("results")}>Results</button>
      </div>

      <div className="mark-area" hidden={tab !== "editor"}>
        <div className="editor glass">
          <div className="sel">
            <label className="sr-only" htmlFor="lang">Language</label>
            <select className="field" id="lang" value={lang} onChange={(e) => { setLang(e.target.value); setCode(STARTER[e.target.value]); setResult(null); resetGraph(); }}>
              <option value="python">Python</option><option value="javascript">JavaScript</option>
            </select>
            <label className="sr-only" htmlFor="q">Question</label>
            <select className="field" id="q" value={question} onChange={(e) => setQuestion(e.target.value)}>
              {questions.length ? questions.map((q) => <option key={q} value={q}>{titleCase(q)}</option>) : <option value={question}>{titleCase(question)}</option>}
            </select>
          </div>
          <div className="monaco-wrap">
            <Editor height="100%" language={lang} theme="codecheck" value={code} onChange={(v) => setCode(v ?? "")}
              beforeMount={defineTheme} onMount={(ed, monaco) => { editorRef.current = ed; monacoRef.current = monaco; ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => document.querySelector(".ph .btn-g")?.click()); }}
              options={{ fontSize: 13.5, fontFamily: "JetBrains Mono, monospace", minimap: { enabled: false }, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 12 }, glyphMargin: true, renderLineHighlight: "line" }} />
          </div>
          <div className="ed-foot"><span>{code.split("\n").length} lines · {code.length} chars</span><span>Ctrl + Enter to run</span></div>
        </div>
        <div className="graph-area">
          <div className="canvas" ref={canvasRef} />
          <div className={`status glass ${status.kind}`} aria-live="polite">
            <div className="t"><span><i className="dotx" />{status.text}</span><b>{status.time}</b></div>
            {status.msg && <div className="msg">{status.msg}</div>}
            <div className="scores">
              <div>Readability<b className="g" ref={(el) => (scoreRefs.current[0] = el)}>–</b></div>
              <div>Efficiency<b className={result && result.efficiency_score >= 5 ? "g" : "r"} ref={(el) => (scoreRefs.current[1] = el)}>–</b></div>
              <div>Similarity<b ref={(el) => (scoreRefs.current[2] = el)}>–</b></div>
            </div>
          </div>
        </div>
      </div>

      <div className="results" hidden={tab !== "results"}>
        {!result ? (
          <div className="empty"><b>No results yet</b>Run a review from the Editor tab to see bugs, scores and an improved version here.</div>
        ) : (
          <>
            <div className="rc"><small>Readability</small><span className="bv" style={{ color: (result.readability_score ?? 0) >= 5 ? "var(--green)" : "var(--red)" }}>{result.readability_score ?? "–"}/10</span></div>
            <div className="rc"><small>Efficiency</small><span className="bv" style={{ color: (result.efficiency_score ?? 0) >= 5 ? "var(--green)" : "var(--red)" }}>{result.efficiency_score ?? "–"}/10</span></div>
            <div className="rc"><small>Similarity to model answer</small><span className="bv">{result.similarity_score != null ? `${result.similarity_score}%` : "n/a"}</span></div>
            <div className="rc"><small>Result</small><span className="bv" style={{ fontSize: 30, marginTop: 14, color: result.pass_status ? "var(--green)" : "var(--red)" }}>{result.pass_status ? "Passed" : "Needs work"}</span></div>
            <div className="rc wide"><small>Bugs and suggestions</small>
              <ul>
                {(result.errors || []).map((e, i) => <li key={"e" + i}><b className="bad">Bug:</b> {e}</li>)}
                {(result.suggestions || []).map((s, i) => <li key={"s" + i}><b>Suggestion:</b> {s}</li>)}
                {!result.errors?.length && !result.suggestions?.length && <li><b className="ok">No issues found.</b></li>}
              </ul>
            </div>
            <div className="rc wide"><small>Improved version</small>
              {result.corrected_code ? (<><pre>{result.corrected_code}</pre><button className="btn btn-o" style={{ marginTop: 12 }} onClick={() => copy(result.corrected_code)}>Copy improved version</button></>)
                : <ul><li>No improved version was returned for this review.</li></ul>}
            </div>
          </>
        )}
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </section>
  );
}
