import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { applyTheme, readTheme, THEME_KEY, ThemeContext } from "@/lib/theme";

export default function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readTheme);

  useLayoutEffect(() => {
    applyTheme(theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* The current visit still uses the selected theme. */ }
  }, [theme]);

  useEffect(() => {
    const syncTheme = (event) => {
      if (event.key === THEME_KEY) setTheme(event.newValue === "light" ? "light" : "dark");
    };
    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);

  const value = useMemo(() => ({ theme, toggleTheme: () => setTheme((current) => current === "dark" ? "light" : "dark") }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
