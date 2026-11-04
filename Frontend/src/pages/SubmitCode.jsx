import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { createGraph, ICON, countUp, sleep } from "@/lib/graph";
import { getSamples, submitCode, errorMessage, titleCase, fileName, SUPPORTED_LANGUAGES, languageInfo, isPerfect, reviewLabel, MAX_CODE_CHARS, MAX_TASK_CHARS } from "@/lib/api";
import { defineTheme } from "@/lib/editorTheme";
import { useTheme } from "@/lib/theme";
import PageActions from "@/components/PageActions";

const CUSTOM_QUESTION = "__custom__";

export default function SubmitCode() {
  const { theme } = useTheme();
  const [params] = useSearchParams();
  const navigation = useLocation();
  const [samples, setSamples] = useState([]);
  const [lang, setLang] = useState(languageInfo(params.get("lang"))?.id || "python");
  const [question, setQuestion] = useState(params.get("q") || CUSTOM_QUESTION);
  const [code, setCode] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [tab, setTab] = useState("editor");
  const [status, setStatus] = useState({ kind: "", text: "Ready · press Run review", time: "" });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const canvasRef = useRef(null), graphRef = useRef(null), scoreRefs = useRef([]);
  const editorRef = useRef(null), monacoRef = useRef(null), decoRef = useRef([]);
  const activeReviewRef = useRef(null), reviewVersionRef = useRef(0);
  const initialSampleRef = useRef(params.get("q") && params.get("q") !== CUSTOM_QUESTION ? { language: lang, title: params.get("q") } : null);

  useEffect(() => { getSamples().then(setSamples).catch(() => {}); }, []);
  useEffect(() => {
    const requested = initialSampleRef.current;
    if (!requested || !samples.length) return;
    initialSampleRef.current = null;
    const sample = samples.find((s) => s.language === requested.language && s.question_title === requested.title);
    if (sample) {
      setCode((current) => current || sample.ideal_code);
      setStatus({ kind: "", text: "Sample loaded · edit it or run a review", time: "" });
    }
  }, [samples]);
  useEffect(() => {
    cancelReview();
    setResult(null); resetGraph(); setTab("editor");
    if (params.get("new")) {
      initialSampleRef.current = null;
      setQuestion(CUSTOM_QUESTION); setCode(""); setTaskDescription("");
      setStatus({ kind: "", text: "Paste your code and press Run review", time: "" });
    } else if (params.get("q")) {
      const language = languageInfo(params.get("lang"))?.id || "python";
      const title = params.get("q").toLowerCase();
      setLang(language); setQuestion(title); setCode("");
      initialSampleRef.current = { language, title };
      const sample = samples.find((s) => s.language === language && s.question_title === title);
      if (sample) { initialSampleRef.current = null; setCode(sample.ideal_code); }
      setStatus({ kind: "", text: "Ready · press Run review", time: "" });
    }
  }, [navigation.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const questions = useMemo(() => samples.filter((s) => s.language === lang).map((s) => s.question_title)
    .sort((a, b) => a === "two sum" ? -1 : b === "two sum" ? 1 : a.localeCompare(b)), [samples, lang]);
  useEffect(() => { if (question !== CUSTOM_QUESTION && questions.length && !questions.includes(question.toLowerCase())) setQuestion(questions[0]); }, [questions]); // eslint-disable-line react-hooks/exhaustive-deps
  const isCustom = question === CUSTOM_QUESTION;
  const file = fileName(isCustom ? "custom code" : question, lang);
  const problem = samples.find((sample) => sample.language === lang && sample.question_title === question);
  const perfect = isPerfect(result);
  const resultLabel = reviewLabel(result);
  const hasCodeChanges = Boolean(result?.corrected_code &&
    result.corrected_code.replace(/\r\n/g, "\n").trimEnd() !== code.replace(/\r\n/g, "\n").trimEnd());

  // build the review workflow once
  useEffect(() => {
    const g = createGraph(canvasRef.current, 1000, 680, "flat");
    g.node("trig", 60, 230, 130, 130, `<div class="card"><div class="c">${ICON.code}</div></div><div class="cap">When code<br>is submitted</div>`, "",
      { k: "Trigger", t: "When code is submitted", b: "Starts when you press Run review. Sends your code, language and question to the agent.", w: [0] });
    g.node("agent", 360, 235, 240, 120, `<div class="card"><div>${ICON.bot(40)}<div class="ttl">CodeCheck AI<span>Review Agent</span></div></div></div>`, "",
      { k: "Agent", t: "Review Agent", b: "Sends your code to Google Gemini and validates its structured review. Submitted code is not executed.", s: [["Model", "Gemini"], ["Assessment", "Static AI review"]], w: [0, 1, 2, 3] });
    g.node("report", 780, 235, 130, 120, `<div class="card"><div class="c">${ICON.doc}</div></div><div class="cap">Review report<small>5 outputs</small></div>`, "",
      { k: "Output", t: "Review report", b: "Bugs, suggestions, readability and efficiency scores, similarity to the model answer and an improved version.", w: [1, 4] });
    g.node("model", 270, 470, 110, 100, `<div class="card"><div class="c">${ICON.spark}</div></div><div class="cap">Gemini<small>chat model</small></div>`, "",
      { k: "Chat model", t: "Google Gemini", b: "The configured Gemini model reviews your code. Provider quotas depend on the model and Google project; the app also limits requests per account.", s: [["Provider", "Google Gemini"], ["Quota", "Project-dependent"]], w: [2] });
    g.node("mem", 470, 490, 110, 100, `<div class="card"><div class="c">${ICON.lib}</div></div><div class="cap">Model answers<small>memory</small></div>`, "",
      { k: "Memory", t: "Model answers", b: "Used to calculate reference similarity for sample exercises. Custom code is reviewed independently of these answers.", s: [["Method", "difflib"], ["Similar at", "70%+"]], w: [3] });
    g.node("db", 740, 470, 210, 100, `<div class="card"><div style="gap:10px;padding:0 16px">${ICON.db}<div class="ttl" style="font-size:20px">Database<span style="font-size:16px">review history</span></div></div></div>`, "",
      { k: "Storage", t: "Application database", b: "Completed reviews are saved to the configured application database and appear in your dashboard and history.", w: [4] });
    g.wire(g.P("trig", "r"), g.P("agent", "l"), { label: "1 item", step: 0, spikes: true });
    g.wire(g.P("agent", "r"), g.P("report", "l"), { label: "1 item", step: 2, spikes: true });
    g.wire(g.P("agent", "b", 0.25), g.P("model", "t"), { v: true, label: "Chat model", at: 0.25, step: 1, spikes: true });
    g.wire(g.P("agent", "b", 0.55), g.P("mem", "t"), { v: true, white: true, label: "Memory", at: 0.75, step: 1, spikes: true });
    g.wire(g.P("report", "b"), g.P("db", "t"), { v: true, label: "Save", at: 0.81, step: 3, spikes: true });
    graphRef.current = g;
    return () => { cancelReview(false); g.destroy(); graphRef.current = null; };
  }, []);

  useEffect(() => {
    const g = graphRef.current;
    if (!g) return;
    g.nodes.mem.el.classList.toggle("inactive", isCustom);
    g.nodes.mem.el.querySelector(".cap small").textContent = isCustom ? "not used" : "memory";
    g.wires[3].step = isCustom ? -1 : 1;
    g.wires[3].g.classList.toggle("inactive-wire", isCustom);
  }, [isCustom]);

  function resetGraph() {
    const g = graphRef.current; if (!g) return;
    Object.keys(g.nodes).forEach((id) => g.unset(id, "on", "done", "work", "fail"));
    scoreRefs.current.forEach((el) => el && (el.textContent = "–"));
    decoRef.current = editorRef.current?.deltaDecorations(decoRef.current, []) || [];
  }

  function loadSampleCode(title = question, language = lang) {
    cancelReview();
    initialSampleRef.current = null;
    const sample = samples.find((s) => s.language === language && s.question_title === title);
    const loadedCode = sample?.ideal_code || (title === "two sum" ? languageInfo(language).starter : "");
    setLang(language);
    setQuestion(title);
    if (title === CUSTOM_QUESTION && question !== CUSTOM_QUESTION) setTaskDescription("");
    setCode(loadedCode);
    editorRef.current?.setValue(loadedCode);
    setResult(null);
    resetGraph();
    setStatus({ kind: "", text: title === CUSTOM_QUESTION ? "Paste your code and press Run review" : sample ? "Sample loaded · edit it or run a review" : "Write your solution for " + titleCase(title), time: "" });
  }

  function changeLanguage(language) {
    const title = isCustom ? CUSTOM_QUESTION : samples.some((s) => s.language === language && s.question_title === question) ? question : "two sum";
    loadSampleCode(title, language);
  }

  // highlight lines mentioned by the AI ("line 3", "lines 2-3")
  function markLines(items) {
    const ed = editorRef.current, monaco = monacoRef.current; if (!ed || !monaco) return;
    const ranges = [];
    items.forEach((t) => { const m = t.match(/lines?\s+(\d+)(?:\s*(?:-|–|to|and)\s*(\d+))?/i); if (m) ranges.push([+m[1], +(m[2] || m[1])]); });
    decoRef.current = ed.deltaDecorations(decoRef.current, ranges.map(([a, b]) => ({ range: new monaco.Range(a, 1, b, 1), options: { isWholeLine: true, className: "cc-bad-line", glyphMarginClassName: "cc-bad-glyph" } })));
  }

  function cancelReview(updateState = true) {
    reviewVersionRef.current += 1;
    activeReviewRef.current?.abort();
    activeReviewRef.current = null;
    if (updateState) setRunning(false);
  }

  async function run() {
    if (running || activeReviewRef.current) return;
    if (!code.trim()) { setStatus({ kind: "err", text: "Write or paste some code first", time: "" }); return; }
    if (code.length > MAX_CODE_CHARS) { setStatus({ kind: "err", text: `Use at most ${MAX_CODE_CHARS.toLocaleString()} characters per review`, time: "" }); return; }
    const g = graphRef.current;
    if (!g) return;
    const controller = new AbortController(), version = ++reviewVersionRef.current;
    activeReviewRef.current = controller;
    const location = window.location.pathname + window.location.search;
    const current = () => activeReviewRef.current === controller && reviewVersionRef.current === version && !controller.signal.aborted && graphRef.current === g && window.location.pathname + window.location.search === location;
    setRunning(true); setTab("editor"); resetGraph(); setResult(null);
    const t0 = performance.now();
    // Handle rejection immediately while the workflow animation is running.
    const request = submitCode({ language: lang, question_title: isCustom ? "" : question, code,
      review_mode: isCustom ? "custom" : "exercise", task_description: isCustom ? taskDescription : "" }, controller.signal)
      .then((data) => ({ data }), (error) => ({ error }));
    setStatus({ kind: "live", text: `Reading ${file}`, time: "" });
    g.set("trig", "on", "done"); g.pulse(0); await sleep(1100);
    if (!current()) return;
    g.unset("trig", "on"); g.set("agent", "on", "work"); setStatus({ kind: "live", text: "Agent reviewing with Gemini…", time: "" });
    g.pulse(1); await sleep(1000); if (!current()) return; g.set("model", "on"); if (!isCustom) g.set("mem", "on");
    let data;
    try {
      const response = await request;
      if (!current()) return;
      if (response.error) throw response.error;
      data = response.data;
    }
    catch (err) {
      if (!current()) return;
      g.unset("agent", "work", "on"); g.unset("model", "on"); g.unset("mem", "on"); g.set("agent", "fail");
      setStatus({ kind: "err", text: "Review failed", time: "", msg: errorMessage(err) }); activeReviewRef.current = null; setRunning(false); return;
    }
    g.unset("model", "on"); g.unset("mem", "on"); g.unset("agent", "work", "on"); g.set("agent", "done");
    g.pulse(2); await sleep(1000); if (!current()) return; g.set("report", "on", "done");
    const [s1, s2, s3] = scoreRefs.current;
    if (data.readability_score == null) s1.textContent = "n/a"; else countUp(s1, data.readability_score, "/10", 0, controller.signal);
    if (data.efficiency_score == null) s2.textContent = "n/a"; else countUp(s2, data.efficiency_score, "/10", 0, controller.signal);
    if (data.similarity_score != null) countUp(s3, data.similarity_score, "%", 0, controller.signal); else s3.textContent = "n/a";
    markLines([...(data.errors || []), ...(data.missing_items || []), ...(data.suggestions || [])]);
    g.pulse(3); await sleep(1000); if (!current()) return; g.unset("report", "on"); g.set("db", "on", "done"); await sleep(400); if (!current()) return; g.unset("db", "on");
    setStatus({ kind: "ok", text: "Completed · saved to dashboard", time: ((performance.now() - t0) / 1000).toFixed(1) + "s" });
    setResult(data); activeReviewRef.current = null; setRunning(false);
  }

  const copy = (txt) => { navigator.clipboard?.writeText(txt).catch(() => {}); flash("Improved version copied"); };
  function applyImproved() {
    if (!result?.corrected_code) return;
    setCode(result.corrected_code);
    resetGraph();
    setResult(null);
    setTab("editor");
    setStatus({ kind: "", text: "Improved code applied · run a new review", time: "" });
    editorRef.current?.focus();
    flash("Improved version applied to editor");
  }
  const [toast, setToast] = useState("");
  function editCode(value) {
    const next = value ?? "";
    if (next === code) return;
    if (activeReviewRef.current) cancelReview();
    setCode(next);
    if (result) {
      setResult(null);
      resetGraph();
      setStatus({ kind: "", text: "Code changed · run a new review", time: "" });
    }
  }
  const flash = (t) => { setToast(t); setTimeout(() => setToast(""), 1800); };

  return (
    <section className="page" aria-labelledby="h-mark">
      <style>{`.cc-bad-line { background: rgba(255,90,80,.12); } .cc-bad-glyph { background: #ff8b80; width: 3px !important; margin-left: 4px; }`}</style>
      <div className="ph">
        <h1 id="h-mark">Code Review Agent<span>/{file}</span></h1>
        {result && <span className={`tag ${result.pass_status ? "green" : "red"} ${perfect ? "perfect" : ""}`}>{resultLabel}</span>}
        <span className="sp" />
        <PageActions><button className="btn btn-g" onClick={run} disabled={running}>
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>{running ? "Reviewing…" : "Run review"}
        </button></PageActions>
      </div>
      <div className="tabs" role="tablist" aria-label="Review views">
        <button role="tab" aria-selected={tab === "editor"} onClick={() => setTab("editor")}>Editor</button>
        <button role="tab" aria-selected={tab === "results"} onClick={() => setTab("results")}>Results</button>
      </div>

      <div className="mark-area" hidden={tab !== "editor"}>
        <div className="editor glass">
          <div className="sel">
            <label className="sr-only" htmlFor="lang">Language</label>
            <select className="field" id="lang" value={lang} disabled={running} onChange={(e) => changeLanguage(e.target.value)}>
              {SUPPORTED_LANGUAGES.map((language) => <option key={language.id} value={language.id}>{language.name}</option>)}
            </select>
            <label className="sr-only" htmlFor="q">Question</label>
            <select className="field" id="q" value={question} disabled={running} onChange={(e) => loadSampleCode(e.target.value)}>
              <option value={CUSTOM_QUESTION}>Custom code (blank editor)</option>
              {questions.map((q) => <option key={q} value={q}>{titleCase(q)}</option>)}
            </select>
          </div>
          {isCustom && <div className="custom-task">
            <label htmlFor="task-description">What should this code do? (optional)</label>
            <textarea className="field task-description" id="task-description" rows={2} disabled={running} maxLength={MAX_TASK_CHARS}
              placeholder="Describe the expected behavior so missing requirements can be checked."
              value={taskDescription} onChange={(e) => { setTaskDescription(e.target.value); setResult(null); resetGraph(); setStatus({ kind: "", text: "Requirements updated · run a new review", time: "" }); }} />
          </div>}
          {problem?.description && <p className="question-description">{problem.description}</p>}
          <div className="monaco-wrap">
            <Editor height="100%" language={languageInfo(lang).monaco} theme={theme === "light" ? "codecheck-light" : "codecheck"} value={code} onChange={editCode}
              beforeMount={defineTheme} onMount={(ed, monaco) => { editorRef.current = ed; monacoRef.current = monaco; ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => document.querySelector(".ph .btn-g")?.click()); }}
              options={{ fontSize: 16, lineHeight: 26, fontFamily: "JetBrains Mono, monospace", minimap: { enabled: false }, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 12 }, glyphMargin: true, renderLineHighlight: "line", autoIndent: "brackets", formatOnPaste: false, insertSpaces: true, detectIndentation: false, tabSize: 4, readOnly: running }} />
          </div>
          <div className="ed-foot"><span>{code.split("\n").length} lines · {code.length} chars</span>{!isCustom && <button type="button" className="load-sample" disabled={running || !problem} onClick={() => loadSampleCode()}>Load sample code</button>}<span>Ctrl + Enter to run</span></div>
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
            <div className="rc"><small>Code similarity to reference</small><span className="bv">{result.similarity_score != null ? `${result.similarity_score}%` : "n/a"}</span><p>{isCustom ? "Custom review: no sample answer is used." : "Normalized code match. Correctness is assessed separately."}</p></div>
            <div className="rc"><small>AI review result</small><span className={`bv ${perfect ? "perfect" : ""}`} style={{ fontSize: 30, marginTop: 14, color: result.pass_status ? "var(--green)" : "var(--red)" }}>{resultLabel}</span><p>{result.correctness_reason}</p><small>Static AI assessment; code was not executed.</small></div>
            <div className="rc wide"><small>Bugs, missing items and suggestions</small>
              <ul>
                {(result.errors || []).map((e, i) => <li key={"e" + i}><b className="bad">Bug:</b> {e}</li>)}
                {(result.missing_items || []).map((item, i) => <li key={"m" + i}><b className="bad">Missing:</b> {item}</li>)}
                {(result.suggestions || []).map((s, i) => <li key={"s" + i}><b>Suggestion:</b> {s}</li>)}
                {!result.errors?.length && !result.missing_items?.length && !result.suggestions?.length && <li><b className={result.review_complete ? "ok" : "bad"}>{result.review_complete ? "No issues reported by the AI." : "Incomplete feedback. Run a new review before relying on these results."}</b></li>}
              </ul>
            </div>
            <div className="rc wide"><small>{hasCodeChanges ? "Improved version" : "Code changes"}</small>
              {hasCodeChanges ? (<><pre>{result.corrected_code}</pre><div className="result-actions"><button className="btn btn-o" onClick={() => copy(result.corrected_code)}>Copy improved version</button><button className="btn btn-g" onClick={applyImproved}>Apply to editor</button></div></>)
                : <ul><li>{result.corrected_code ? (perfect ? "No changes needed. The reviewer kept your submitted code unchanged." : "The reviewer returned the same code; no revised version is available to apply.") : "No improved version was returned for this review."}</li></ul>}
            </div>
          </>
        )}
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </section>
  );
}
