import { useEffect, useState } from "react";
import { errorMessage, getAccessUsers, getSignIns, setUserAccess } from "@/lib/api";
import PageActions from "@/components/PageActions";

const date = (value) => new Date(value).toLocaleString();
const providerName = (id) => ({ google: "Google", github: "GitHub", microsoft: "Microsoft", email: "Email" })[id] || id;
export default function AccessLog() {
  const [tab, setTab] = useState("users"), [offset, setOffset] = useState(0);
  const [data, setData] = useState(null), [error, setError] = useState(""), [reload, setReload] = useState(0);
  const [changing, setChanging] = useState(null), [notice, setNotice] = useState("");
  useEffect(() => {
    let alive = true;
    (tab === "users" ? getAccessUsers : getSignIns)(offset).then((value) => { if (alive) setData(value); })
      .catch((err) => { if (alive) setError(errorMessage(err)); });
    return () => { alive = false; };
  }, [tab, offset, reload]);
  const load = (nextTab, nextOffset = 0) => { setData(null); setError(""); setNotice(""); setTab(nextTab); setOffset(nextOffset); };
  async function changeAccess(item) {
    if (changing || item.is_owner) return;
    setChanging(item.id); setError(""); setNotice("");
    try {
      const updated = await setUserAccess(item.id, !item.is_blocked);
      setData((previous) => previous && ({ ...previous, items: previous.items.map((row) => row.id === item.id ? { ...row, ...updated } : row) }));
      setNotice(`${item.email || item.name} ${updated.is_blocked ? "blocked and signed out" : "unblocked. They can sign in again"}.`);
    } catch (err) { setError(errorMessage(err)); }
    finally { setChanging(null); }
  }
  return <section className="page" aria-labelledby="h-access">
    <div className="ph"><h1 id="h-access">User access<span>/owner only</span></h1><span className="sp" />
      <PageActions><button className="btn btn-o" disabled={Boolean(changing)} onClick={() => { setData(null); setError(""); setNotice(""); setReload((value) => value + 1); }}>Refresh</button></PageActions>
    </div>
    <p className="access-note">Only you can manage user access. Blocking signs a user out and prevents access until you unblock them.</p>
    <div className="tabs" role="tablist" aria-label="Access records">
      <button role="tab" disabled={Boolean(changing)} aria-selected={tab === "users"} onClick={() => load("users")}>Users</button>
      <button role="tab" disabled={Boolean(changing)} aria-selected={tab === "events"} onClick={() => load("events")}>Sign-in history</button>
    </div>
    {error && <div className="notice err" role="alert">{error}</div>}
    {notice && <div className="notice ok" role="status">{notice}</div>}
    {!data && !error && <div className="loading" role="status">Loading access records…</div>}
    {data && <><div className="access-summary"><b>{data.total} {tab === "users" ? "accounts" : "sign-ins"}</b>{tab === "users" && <span>{data.total_sign_ins} total sign-ins</span>}</div>
      <div className="hist glass" role="tabpanel"><table><thead><tr><th>Name</th><th>Email</th><th>Provider</th>
        {tab === "users" ? <><th>Status</th><th>Access</th><th>First sign-in</th><th>Last sign-in</th><th>Last active</th><th>Sign-ins</th><th>Reviews</th></> : <th>Signed in</th>}
      </tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td>{item.name}{item.is_owner && <span className="access-owner">Owner</span>}</td><td>{item.email || "Not provided"}{tab === "users" && item.email && <small className="access-email-status">{item.email_verified ? "Verified" : "Not verified"}</small>}</td><td>{providerName(item.provider)}</td>
        {tab === "users" ? <><td><span className={`access-status ${item.is_blocked ? "blocked" : "active"}`}>{item.is_blocked ? "Blocked" : "Active"}</span></td>
          <td className="access-controls">{item.is_owner ? <span className="access-protected">Your account</span> : <button className={`btn btn-o access-action ${item.is_blocked ? "" : "block"}`} disabled={Boolean(changing)} onClick={() => changeAccess(item)} aria-label={`${item.is_blocked ? "Unblock" : "Block"} ${item.email || item.name}`}>{changing === item.id ? "Updating…" : item.is_blocked ? "Unblock" : "Block"}</button>}</td>
          <td>{date(item.first_login_at)}</td><td>{date(item.last_login_at)}</td><td>{date(item.last_seen_at)}</td><td>{item.login_count}</td><td>{item.review_count}</td></> : <td>{date(item.signed_in_at)}</td>}
      </tr>)}</tbody></table>{!data.items.length && <p className="loading">No sign-ins recorded yet.</p>}</div>
      <div className="access-pagination"><button className="btn btn-o" disabled={Boolean(changing) || offset === 0} onClick={() => load(tab, Math.max(0, offset - 50))}>Previous</button>
        <span>{data.total ? offset + 1 : 0}–{Math.min(offset + 50, data.total)} of {data.total}</span>
        <button className="btn btn-o" disabled={Boolean(changing) || offset + 50 >= data.total} onClick={() => load(tab, offset + 50)}>Next</button></div>
    </>}
  </section>;
}
