import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { errorMessage, signOut } from "@/lib/api";

export default function AccountMenu() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const host = useRef(null), trigger = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (event) => { if (!host.current?.contains(event.target)) setOpen(false); };
    const escape = (event) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  const initials = user.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  const provider = ({ google: "Google", github: "GitHub", microsoft: "Microsoft", email: "email and password" })[user.provider || "email"];
  async function logout() {
    setBusy(true); setError("");
    try { await signOut(); } catch (err) { setError(errorMessage(err)); setBusy(false); }
  }
  return <div className="account" ref={host}>
    <button className="me" ref={trigger} aria-label={`Account: ${user.name}`} aria-expanded={open} aria-controls="account-panel" title={user.name} onClick={() => setOpen((value) => !value)}>
      {initials}{user.picture && !imageFailed && <img src={user.picture} alt="" referrerPolicy="no-referrer" onError={() => setImageFailed(true)} />}
    </button>
    {open && <section id="account-panel" className="account-panel" aria-label="Your account">
      <small>Signed in with {provider}</small><b>{user.name}</b><span>{user.email || "Email not provided"}</span>
      {user.provider_subject && <details className="account-details"><summary>Account details</summary><small>Account ID</small><code>{user.provider_subject}</code></details>}
      {user.is_owner && <Link to="/access" onClick={() => setOpen(false)}>View user access</Link>}
      <button onClick={logout} disabled={busy}>{busy ? "Signing out…" : "Sign out"}</button>
      {error && <p role="alert">{error}</p>}
    </section>}
  </div>;
}
