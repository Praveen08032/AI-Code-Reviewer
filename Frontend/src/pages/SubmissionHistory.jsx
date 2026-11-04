import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageActions from "@/components/PageActions";
import { getHistory, errorMessage, languageName, languageBadge, isPerfect, reviewLabel } from "@/lib/api";

const firstLine = (code = "") => (code.split("\n").find((l) => l.trim()) || "(empty)").trim();

export default function SubmissionHistory() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    getHistory().then((d) => setRows([...d].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))))
      .catch((e) => { setError(errorMessage(e)); setRows([]); });
  }, []);

  const passed = rows?.filter((r) => r.pass_status).length ?? 0;
  const toggle = (id) => setOpen((o) => (o === id ? null : id));

  return (
    <section className="page" aria-labelledby="h-hist">
      <div className="ph"><h1 id="h-hist">History<span>/AI reviews</span></h1>{rows?.length > 0 && <span className="tag green">{passed} of {rows.length} passed AI review</span>}<span className="sp" /><PageActions /></div>
      {error && <div className="notice err" style={{ marginTop: 18 }}>{error}</div>}
      <div className="hist glass">
        {rows === null && <p className="loading">Loading…</p>}
        {rows && !rows.length && !error && <div className="empty"><b>No reviews yet</b><p style={{ marginBottom: 16 }}>Your submissions and their reviews will appear here.</p><Link className="btn btn-g" to="/submit?new=1">Mark my code</Link></div>}
        {rows?.length > 0 && (
          <table>
            <thead><tr><th>Run</th><th>Submission</th><th>Language</th><th>Readability</th><th>Efficiency</th><th>Similarity</th><th>Result</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.id}>
                  <tr className="row" tabIndex={0} aria-expanded={open === r.id} onClick={() => toggle(r.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(r.id); } }}>
                    <td>#{r.id}</td><td><code>{firstLine(r.code)}</code></td><td><span className="lang" title={languageName(r.language)}>{languageBadge(r.language)}</span> {languageName(r.language)}</td>
                    <td>{r.readability_score ?? "–"}/10</td><td>{r.efficiency_score ?? "–"}/10</td><td>{r.similarity_score != null ? `${r.similarity_score}%` : "–"}</td>
                    <td><span className={`pill ${r.pass_status ? "ok" : "no"} ${isPerfect(r) ? "perfect" : ""}`}>{reviewLabel(r)}</span></td>
                    <td style={{ color: "var(--muted)" }}>{new Date(r.created_at).toLocaleString()}</td>
                  </tr>
                  {open === r.id && (
                    <tr className="det"><td colSpan={8}><div className="det-in">
                      <div><small>Bugs and missing items</small>{r.errors || "No bugs reported"}{r.missing_items?.length > 0 && <ul>{r.missing_items.map((item, i) => <li key={i}>{item}</li>)}</ul>}</div>
                      <div><small>Suggestions</small>{r.suggestions || "None"}</div>
                      <div><small>Improved version</small>{r.corrected_code ? <pre>{r.corrected_code}</pre> : "Not provided"}</div>
                    </div></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
