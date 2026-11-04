import { useTheme } from "@/lib/theme";

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return <button className="theme-toggle" type="button" role="switch" aria-label="Night mode" aria-checked={theme === "dark"}
    onClick={toggleTheme}>
    <span className="theme-toggle-track" aria-hidden="true">
      <span className="theme-toggle-scene day">
        <svg className="theme-toggle-cloud" viewBox="0 0 40 24"><path d="M9 21h23a7 7 0 0 0-1.5-13.8A10 10 0 0 0 12 6a7.5 7.5 0 1 0-3 15Z" fill="currentColor" /></svg>
      </span>
      <span className="theme-toggle-scene night">
        <svg className="theme-toggle-stars" viewBox="0 0 80 40" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"><path d="M14 7v6m-3-3h6M31 24v4m-2-2h4" /><circle cx="32" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="10" cy="28" r=".8" fill="currentColor" stroke="none" /></svg>
      </span>
      <span className="theme-toggle-thumb">
        <svg className="theme-toggle-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="3.5" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        <svg className="theme-toggle-moon" viewBox="0 0 24 24" fill="currentColor"><path d="M20.5 13.5A8.5 8.5 0 0 1 10.5 3a8.5 8.5 0 1 0 10 10.5Z" /></svg>
      </span>
    </span>
  </button>;
}
