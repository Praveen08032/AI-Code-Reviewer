import axios from "axios";
import { STARTER_CODE } from "./starters";

export const SUPPORTED_LANGUAGES = [
  { id: "python", name: "Python", extension: ".py", badge: "PY" },
  { id: "javascript", name: "JavaScript", extension: ".js", badge: "JS" },
  { id: "typescript", name: "TypeScript", extension: ".ts", badge: "TS" },
  { id: "java", name: "Java", extension: ".java", badge: "JAVA" },
  { id: "cpp", name: "C++", extension: ".cpp", badge: "C++" },
  { id: "csharp", name: "C#", extension: ".cs", badge: "C#" },
  { id: "go", name: "Go", extension: ".go", badge: "GO" },
  { id: "rust", name: "Rust", extension: ".rs", badge: "RS" },
  { id: "php", name: "PHP", extension: ".php", badge: "PHP" },
  { id: "ruby", name: "Ruby", extension: ".rb", badge: "RB" },
].map((language) => ({ ...language, monaco: language.id, starter: STARTER_CODE[language.id] }));

export const languageInfo = (id) => SUPPORTED_LANGUAGES.find((language) => language.id === id);
export const languageName = (id) => languageInfo(id)?.name || id;
export const languageBadge = (id) => languageInfo(id)?.badge || id?.toUpperCase();
export const isPerfect = (review) => review?.is_perfect === true;
export const reviewLabel = (review) => review?.review_complete === false ? "Incomplete review" : isPerfect(review) ? "Top AI score" : review?.pass_status ? "AI review passed" : "Needs work";
export const MAX_CODE_CHARS = 20000;
export const MAX_TASK_CHARS = 4000;

const API = (import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://localhost:9055" : "")).replace(/\/+$/, "");
export const api = axios.create({ baseURL: API });
// Authentication goes through the frontend's /auth proxy, so its HttpOnly
// session cookie works even when Netlify and Render have different domains.
const auth = axios.create({ baseURL: "", withCredentials: true });
let accessToken = null, accountId = null, authVersion = 0, refreshPromise = null, challengePromise = null;
const listeners = new Set();
export const AUTH_CHANGE_KEY = "codecheck.auth.changed";
export const subscribeAuth = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
const publishSession = (data) => {
  accessToken = data?.access_token || null;
  accountId = data?.user?.id || null;
  listeners.forEach((listener) => listener(data?.user || null));
};
const announceAuthChange = () => {
  try { localStorage.setItem(AUTH_CHANGE_KEY, `${Date.now()}-${Math.random()}`); } catch { /* Server authorization still applies. */ }
};
const invalidateRefresh = () => { authVersion += 1; refreshPromise = null; };
export const clearCachedIdentity = () => { invalidateRefresh(); publishSession(null); };
export const getAuthConfig = () => auth.get("/auth/config").then((r) => {
  if (typeof r.data?.configured !== "boolean") throw new Error("Sign-in settings could not be loaded. Please contact the site owner.");
  return r.data;
});
export const getLoginChallenge = () => {
  if (!challengePromise) challengePromise = auth.post("/auth/challenge").then((r) => {
    if (!r.data?.nonce) throw new Error("Google sign-in could not be started. Please try again.");
    return r.data;
  }).finally(() => { challengePromise = null; });
  return challengePromise;
};
export const restoreSession = () => {
  if (!refreshPromise) {
    const version = authVersion;
    const pending = auth.get("/auth/me").then((r) => {
      if (version !== authVersion) throw new axios.CanceledError("The signed-in account changed.");
      if (!r.data?.user?.id || !r.data?.access_token) throw new Error("Your sign-in session could not be restored. Please try again.");
      publishSession(r.data); return r.data.user;
    }).catch((error) => {
      if (version === authVersion) publishSession(null);
      throw error;
    }).finally(() => { if (refreshPromise === pending) refreshPromise = null; });
    refreshPromise = pending;
  }
  return refreshPromise;
};
export const signInGoogle = (credential) => auth.post("/auth/google", { credential }).then((r) => {
  invalidateRefresh(); publishSession(r.data); announceAuthChange(); return r.data.user;
});
const emailAccount = (path, body) => auth.post(path, body).then((r) => {
  if (r.data?.verification_required && r.data?.challenge_token) {
    clearCachedIdentity();
    return r.data;
  }
  if (!r.data?.user?.id || !r.data?.access_token) throw new Error("Sign-in could not be completed. Please try again.");
  invalidateRefresh(); publishSession(r.data); announceAuthChange(); return r.data.user;
});
export const signInEmail = (body) => emailAccount("/auth/login", body);
export const registerEmail = (body) => emailAccount("/auth/register", body);
export const verifyEmail = (body) => emailAccount("/auth/verify-email", body);
export const resendVerification = (challenge_token) => auth.post("/auth/resend-verification", { challenge_token }).then((r) => r.data);
export const startOAuth = (provider) => auth.post(`/auth/${provider}/start`).then((r) => {
  const url = new URL(r.data.authorization_url);
  const expectedHost = provider === "github" ? "github.com" : provider === "microsoft" ? "login.microsoftonline.com" : null;
  if (!expectedHost || url.protocol !== "https:" || url.hostname !== expectedHost) throw new Error("The sign-in provider returned an invalid address.");
  return url.href;
});
export const signOut = () => auth.post("/auth/logout").then(() => { clearCachedIdentity(); announceAuthChange(); });
api.interceptors.request.use((config) => {
  if (!config.authRetried) config.accountId = accountId;
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
api.interceptors.response.use((response) => response, async (error) => {
  const request = error.config;
  if (error.response?.status === 403 && error.response.data?.detail === "Your account has been blocked by the site owner.") {
    clearCachedIdentity(); announceAuthChange();
  }
  if (error.response?.status === 401 && request && !request.authRetried) {
    request.authRetried = true;
    await restoreSession();
    if (request.accountId !== accountId) throw new axios.CanceledError("The signed-in account changed. Submit from the current account.");
    request.headers.Authorization = `Bearer ${accessToken}`;
    return api(request);
  }
  return Promise.reject(error);
});

const getList = async (path) => {
  const response = await api.get(path);
  if (!Array.isArray(response.data)) {
    throw new Error("The server returned invalid data. Check VITE_API_BASE_URL and restart the frontend.");
  }
  return response.data;
};

export const getSamples = () => getList("/sample-questions");
export const getHistory = () => getList("/submission-history");
export const addSample = (body) => api.post("/add-sample-answer", body).then((r) => r.data);
export const submitCode = (body, signal) => api.post("/submit-code", body, { signal, timeout: 70000 }).then((r) => r.data);
export const listChats = () => getList("/chat/conversations");
export const getChat = (id) => api.get(`/chat/conversations/${encodeURIComponent(id)}`).then((r) => r.data);
export const sendChat = (body) => api.post("/chat/messages", body).then((r) => r.data);
export const deleteChat = (id) => api.delete(`/chat/conversations/${encodeURIComponent(id)}`);
export const clearChatHistory = () => api.delete("/chat/conversations");
export const getAccessUsers = (offset = 0) => api.get("/admin/users", { params: { offset, limit: 50 } }).then((r) => r.data);
export const getSignIns = (offset = 0) => api.get("/admin/sign-ins", { params: { offset, limit: 50 } }).then((r) => r.data);
export const setUserAccess = (id, blocked) => api.patch(`/admin/users/${encodeURIComponent(id)}/access`, { blocked }).then((r) => r.data);

// Turn an API error into a sentence a person can act on
export function errorMessage(err) {
  const responseDetail = err?.response?.data?.detail;
  const detail = typeof responseDetail === "string" ? responseDetail : Array.isArray(responseDetail) ? responseDetail.map((item) => `${item.loc?.at(-1) || "Input"}: ${item.msg}`).join("; ") : "";
  if (err instanceof Error && !axios.isAxiosError(err)) return err.message;
  if (detail.includes("429") || detail.toLowerCase().includes("quota")) {
    const retry = detail.match(/retry in ([\d.]+)s/i);
    return retry
      ? `Gemini's rate limit was reached. Try again in ${Math.ceil(Number(retry[1]))} seconds.`
      : "Gemini's quota was reached. Check your API usage and limits before trying again.";
  }
  if (/504|deadline|timed?\s*out|timeout/i.test(detail)) return "Gemini did not respond in time. Wait a minute and try again.";
  if (/503|high demand|overloaded/i.test(detail)) return "Gemini is busy right now. Wait a minute and try again.";
  if (!err?.response) return "Could not reach the server. It may be waking up, so please try again in a minute.";
  if (typeof detail === "string" && detail && detail.length < 160) return detail;
  return "Something went wrong. Please try again.";
}

export const titleCase = (s = "") => s.replace(/\b\w/g, (c) => c.toUpperCase());
export const fileName = (title = "", lang = "python") =>
  (title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "solution") + (languageInfo(lang)?.extension || ".txt");
