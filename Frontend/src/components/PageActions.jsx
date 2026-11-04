import ThemeToggle from "./ThemeToggle";

export default function PageActions({ children }) {
  return <div className="page-actions"><ThemeToggle />{children}</div>;
}
