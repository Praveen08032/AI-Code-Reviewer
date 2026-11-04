import { createContext, useContext } from "react";

export const THEME_KEY = "codecheck.theme";
export const ThemeContext = createContext(null);

export function readTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "dark";
  } catch { return "dark"; }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("Theme controls must be inside ThemeProvider.");
  return value;
}
