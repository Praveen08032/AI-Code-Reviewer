import { useState } from "react";
import { Link } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { addSample, errorMessage, SUPPORTED_LANGUAGES, languageInfo } from "@/lib/api";
import { defineTheme } from "@/lib/editorTheme";
import { useTheme } from "@/lib/theme";
import PageActions from "@/components/PageActions";

export default function AddSampleAnswer() {
  const { theme } = useTheme();
  const [title, setTitle] = useState("");
  const [lang, setLang] = useState("python");
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState(null);
  const [saving, setSaving] = useState(false);

  async function save(e) {
    e.preventDefault();
    if (!title.trim() || !code.trim()) { setMsg({ kind: "err", text: !title.trim() ? "Enter a question title." : "Write the model answer code." }); return; }
    setSaving(true); setMsg(null);
    try {
      const r = await addSample({ question_title: title, language: lang, ideal_code: code });
      setMsg({ kind: "ok", text: `${r.message} “${title}” can now be practised from the library.` }); setTitle(""); setCode("");
    } catch (err) { setMsg({ kind: "err", text: errorMessage(err) }); }
    setSaving(false);
  }

  return (
    <section className="page" aria-labelledby="h-add">
      <div className="ph"><h1 id="h-add">Add Sample<span>/new model answer</span></h1><span className="sp" /><PageActions><Link className="btn btn-o" to="/sample-questions">Back to library</Link></PageActions></div>
      <form className="form glass" onSubmit={save} noValidate>
        {msg && <div className={`notice ${msg.kind}`} role={msg.kind === "err" ? "alert" : "status"}>{msg.text}</div>}
        <div className="two">
          <div><label htmlFor="title">Question title</label><input className="field" id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Valid Parentheses" /></div>
          <div><label htmlFor="slang">Language</label><select className="field" id="slang" value={lang} onChange={(e) => setLang(e.target.value)}>{SUPPORTED_LANGUAGES.map((language) => <option key={language.id} value={language.id}>{language.name}</option>)}</select></div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          <label htmlFor="ideal">Model answer</label>
          <div className="monaco-wrap" id="ideal">
            <Editor height="100%" language={languageInfo(lang).monaco} theme={theme === "light" ? "codecheck-light" : "codecheck"} value={code} onChange={(v) => setCode(v ?? "")} beforeMount={defineTheme}
        options={{ fontSize: 16, lineHeight: 26, fontFamily: "JetBrains Mono, monospace", minimap: { enabled: false }, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 12 }, autoIndent: "brackets", formatOnPaste: false, insertSpaces: true, detectIndentation: false, tabSize: 4 }} />
          </div>
        </div>
        <div><button className="btn btn-g" type="submit" disabled={saving}>{saving ? "Saving…" : "Save sample answer"}</button></div>
      </form>
    </section>
  );
}
