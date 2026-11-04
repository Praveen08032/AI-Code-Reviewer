import { useEffect, useState } from "react";
import { Code2, Eye, EyeOff, ArrowRight, Mail, LockKeyhole } from "lucide-react";
import { errorMessage, getAuthConfig, signInEmail, registerEmail, verifyEmail, resendVerification } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ThemeToggle from "@/components/ThemeToggle";
import "@/styles/auth.css";

export function SessionLoading() {
  return <div className="auth-loading" role="status"><span className="auth-loading-dot" />Checking your sign-in…</div>;
}

export default function Login({ onSignedIn }) {
  const { user, error: sessionError, retry } = useAuth();
  const [ownerToken, setOwnerToken] = useState(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get("owner-setup") || "";
    return token;
  });
  useEffect(() => {
    if (ownerToken) window.history.replaceState({}, "", window.location.pathname + window.location.search);
  }, [ownerToken]);
  const [creating, setCreating] = useState(Boolean(ownerToken) && !user);
  const [email, setEmail] = useState(user?.email || "");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [verification, setVerification] = useState(null), [code, setCode] = useState("");
  const [mailReady, setMailReady] = useState(null), [tick, setTick] = useState(Date.now());
  useEffect(() => {
    let alive = true;
    getAuthConfig().then((config) => { if (alive) setMailReady(config.email_delivery_ready); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!verification) return;
    const timer = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [verification]);
  useEffect(() => {
    const consume = () => {
      const token = new URLSearchParams(window.location.hash.slice(1)).get("owner-setup");
      if (token) { setOwnerToken(token); setCreating(!user); }
    };
    window.addEventListener("hashchange", consume);
    return () => window.removeEventListener("hashchange", consume);
  }, [user]);

  function switchMode(next) {
    setCreating(next); setVerification(null); setCode(""); setError(""); setPassword(""); setVisible(false);
  }
  function acceptChallenge(result) {
    setVerification({ ...result, resendAt: Date.now() + result.resend_after * 1000 });
    setTick(Date.now()); setCode(""); setPassword(""); setVisible(false);
  }
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await (creating ? registerEmail : signInEmail)({ email, password, owner_token: ownerToken });
      if (result?.verification_required) { acceptChallenge(result); return; }
      setPassword("");
      onSignedIn?.();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function confirmEmail(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await verifyEmail({ challenge_token: verification.challenge_token, code });
      setVerification(null); setCode(""); onSignedIn?.();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function resend() {
    setBusy(true); setError("");
    try { acceptChallenge(await resendVerification(verification.challenge_token)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  const resendSeconds = verification ? Math.max(0, Math.ceil((verification.resendAt - tick) / 1000)) : 0;

  return <div className="auth-shell">
    <header className="auth-top"><a className="auth-brand" href="/" aria-label="CodeCheck AI home"><span aria-hidden="true"><Code2 size={24} /></span>CodeCheck AI</a><ThemeToggle /></header>
    <main className="auth-main">
      <div className="auth-intro"><span className="auth-eyebrow">YOUR CODE. A CLEARER NEXT STEP.</span>
        <h1>Build confidence<br />in every line.</h1><p>Review your code, understand what needs fixing, and keep track of your progress.</p>
        <div className="auth-features"><span>10 programming languages</span><span>Personal review history</span><span>Code assistant</span></div>
      </div>
      <section className="auth-card" aria-labelledby="sign-in-title">
        <div className="auth-card-mark" aria-hidden="true"><Code2 size={34} /></div>
        <h2 id="sign-in-title">{verification ? "Verify your email" : ownerToken ? "Your owner account" : creating ? "Create your account" : "Welcome back"}</h2>
        <p>{verification ? <>Enter the six-digit code sent to <strong>{verification.email}</strong>. It expires in 10 minutes.</> : creating ? "Choose a CodeCheck password. We'll verify your email before you can enter." : "Sign in with the email and password you registered with CodeCheck."}</p>
        {verification ? <form className="auth-form" onSubmit={confirmEmail}>
          <label htmlFor="auth-code">Verification code</label>
          <div className="auth-input"><Mail size={18} aria-hidden="true" /><input id="auth-code" name="code" className="auth-code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required value={code} onChange={(event) => setCode(event.target.value.replace(/[^0-9]/g, ""))} disabled={busy} /></div>
          <small className="auth-hint">Check your inbox and spam folder. Your account stays locked until verification.</small>
          {error && <div className="notice err" role="alert">{error}</div>}
          <button className="btn btn-g auth-submit" type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify email & continue"}<ArrowRight size={18} aria-hidden="true" /></button>
          <div className="auth-code-actions"><button type="button" className="auth-retry" onClick={resend} disabled={busy || resendSeconds > 0}>{resendSeconds ? `Resend code in ${resendSeconds}s` : "Resend code"}</button><button type="button" className="auth-retry" onClick={() => switchMode(creating)} disabled={busy}>Change email</button></div>
        </form> : <>
        <div className="auth-mode" aria-label="Account options">
          <button type="button" aria-pressed={!creating} onClick={() => switchMode(false)} disabled={busy}>Sign in</button>
          <button type="button" aria-pressed={creating} onClick={() => switchMode(true)} disabled={busy}>Create account</button>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label htmlFor="auth-email">Email address</label>
          <div className="auth-input"><Mail size={18} aria-hidden="true" /><input id="auth-email" name="email" type="email" autoComplete="username" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" disabled={busy} /></div>
          <label htmlFor="auth-password">Password</label>
          <div className="auth-input"><LockKeyhole size={18} aria-hidden="true" /><input id="auth-password" name="password" type={visible ? "text" : "password"} autoComplete={creating ? "new-password" : "current-password"} required minLength={creating ? 15 : 1} maxLength={128} aria-describedby={creating ? "password-hint" : undefined} value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} />
            <button type="button" className="auth-reveal" aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} onClick={() => setVisible((value) => !value)}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button>
          </div>
          {creating && <small id="password-hint" className="auth-hint">Use 15 or more characters. Avoid repeated patterns and common passwords.</small>}
          {(error || sessionError) && <div className="notice err" role="alert">{error || sessionError}</div>}
          <button className="btn btn-g auth-submit" type="submit" disabled={busy}>{busy ? (creating ? "Sending code…" : "Signing in…") : creating ? "Create account" : "Sign in"}<ArrowRight size={18} aria-hidden="true" /></button>
        </form>
        {mailReady === false && <p className="auth-delivery-note" role="status">New accounts need email verification. Email delivery is being set up.</p>}
        </>}
        {sessionError && <button className="auth-retry" onClick={retry} disabled={busy}>Check connection again</button>}
        <div className="auth-privacy"><b>A space for your work</b><p>Your reviews and chats stay with your account. Your email and sign-in activity are visible to the site owner.</p></div>
      </section>
    </main><footer className="auth-footer">Your next code review starts here.</footer>
  </div>;
}
