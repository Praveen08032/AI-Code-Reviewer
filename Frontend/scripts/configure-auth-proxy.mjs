import { mkdirSync, writeFileSync } from "node:fs";
import { loadEnv } from "vite";
import { authProxyRules } from "./auth-proxy.mjs";

const environment = { ...loadEnv("production", process.cwd(), ""), ...process.env };
const backend = environment.VITE_API_BASE_URL?.replace(/\/+$/, "");
// Only auth uses the proxy: direct AI requests retain their 60-second timeout.
mkdirSync("public", { recursive: true });
writeFileSync("public/_redirects", authProxyRules(backend, environment.NETLIFY === "true"));
