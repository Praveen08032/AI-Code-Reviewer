import { NavLink, Link, useLocation } from "react-router-dom";

const ITEMS = [
  { to: "/", label: "Dashboard", d: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z", end: true },
  { to: "/submit", label: "Mark code", d: "M8 6l-5 6 5 6M16 6l5 6-5 6" },
  { to: "/sample-questions", label: "Sample library", d: "M4 4h5v16H4zM10 4h4v16h-4zM15 5l4-1 2 15-4 1z", also: ["/add-sample"] },
  { to: "/history-submissions", label: "History", d: "M12 4a8 8 0 100 16 8 8 0 000-16zM12 8v4l3 2" },
];

export default function Rail() {
  const { pathname } = useLocation();
  return (
    <nav className="rail" aria-label="App">
      <div className="logo" title="CodeCheck AI">
        <svg viewBox="0 0 24 24" fill="none" stroke="#4ade5a" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6" /></svg>
      </div>
      <Link className="tile add" to="/submit?new=1" aria-label="New review">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        <span className="tip">New review</span>
      </Link>
      {ITEMS.map((it) => (
        <NavLink key={it.to} to={it.to} end={it.end} aria-label={it.label}
          className={({ isActive }) => `tile ${isActive || it.also?.includes(pathname) ? "active" : ""}`}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={it.d} /></svg>
          <span className="tip">{it.label}</span>
        </NavLink>
      ))}
      <div className="me" title="Praveen Kumar V">PK</div>
    </nav>
  );
}
