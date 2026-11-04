export function authProxyRules(backend, isNetlify = false) {
  const rules = [];
  if (backend) {
    const url = new URL(backend);
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
      throw new Error("VITE_API_BASE_URL must be the HTTPS backend origin, without credentials or a path.");
    }
    rules.push(`/auth/*  ${url.origin}/auth/:splat  200!`);
  } else if (isNetlify) {
    throw new Error("Set VITE_API_BASE_URL to your HTTPS backend origin in Netlify before deploying sign-in.");
  }
  rules.push("/*  /index.html  200");
  return rules.join("\n") + "\n";
}
