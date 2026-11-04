import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageActions from "@/components/PageActions";
import { getSamples, errorMessage, SUPPORTED_LANGUAGES, languageName, languageBadge } from "@/lib/api";

export default function SampleAnswerList() {
  const [samples, setSamples] = useState(null);
  const [error, setError] = useState("");
  const [lang, setLang] = useState("all");
  const [find, setFind] = useState("");
  const [current, setCurrent] = useState(null);
  const [toast, setToast] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    getSamples().then((d) => { setSamples(d); const ts = d.find((s) => s.question_title === "two sum" && s.language === "python") || d[0]; setCurrent(ts?.id ?? null); })
      .catch((e) => { setError(errorMessage(e)); setSamples([]); });
  }, []);

  const list = useMemo(() => (samples || []).filter((s) => (lang === "all" || s.language === lang) && s.question_title.includes(find.trim().toLowerCase())), [samples, lang, find]);
  const sel = list.find((s) => s.id === current) || list[0];
  const flash = (t) => { setToast(t); setTimeout(() => setToast(""), 1800); };

  return (
    <section className="page" aria-labelledby="h-lib">
      <div className="ph">
        <h1 id="h-lib">Sample Library<span>/model answers</span></h1>
        {samples && <span className="tag green">{samples.length} answers</span>}
        <span className="sp" />
        <PageActions><Link className="btn btn-o" to="/add-sample">+ Add sample</Link></PageActions>
      </div>
      {error && <div className="notice err" style={{ marginTop: 18 }}>{error}</div>}
      <div className="lib">
        <div className="lib-list glass">
          <label className="sr-only" htmlFor="find">Search questions</label>
          <input className="field" id="find" type="search" placeholder="Search questions" value={find} onChange={(e) => setFind(e.target.value)} />
          <div className="seg" role="group" aria-label="Language">
            {[{ id: "all", name: "All" }, ...SUPPORTED_LANGUAGES].map((language) => <button key={language.id} aria-pressed={lang === language.id} onClick={() => setLang(language.id)}>{language.name}</button>)}
          </div>
          <div className="qlist">
            {samples === null && <p className="loading">Loading…</p>}
            {samples && !list.length && <p style={{ color: "var(--muted)", padding: 20, textAlign: "center" }}>No questions match “{find}”.</p>}
            {list.map((s) => (
              <button key={s.id} aria-current={s.id === sel?.id} onClick={() => setCurrent(s.id)}>
                <b>{s.question_title}</b><small>{s.ideal_code.split("\n").length} lines</small>
                <span className="lang" title={languageName(s.language)}>{languageBadge(s.language)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="lib-view glass" aria-live="polite">
          {sel ? (
            <>
              <h2>{sel.question_title}</h2>
              <div className="meta">{languageName(sel.language)} · {sel.ideal_code.split("\n").length} lines · model answer</div>
              {sel.description && <p className="question-description">{sel.description}</p>}
              <pre key={sel.id}>{sel.ideal_code.split("\n").map((l, n) => <span className="row" key={n} style={{ animationDelay: `${n * 30}ms` }}><span className="n">{n + 1}</span>{l || " "}</span>)}</pre>
              <div className="acts">
                <button className="btn btn-g" onClick={() => navigate(`/submit?lang=${sel.language}&q=${encodeURIComponent(sel.question_title)}`)}>Try this question</button>
                <button className="btn btn-o" onClick={() => { navigator.clipboard?.writeText(sel.ideal_code).catch(() => {}); flash("Model answer copied"); }}>Copy model answer</button>
              </div>
            </>
          ) : samples && <div className="empty"><b>No sample selected</b>Choose a question on the left, or add a new sample answer.</div>}
        </div>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </section>
  );
}
