import axios from "axios";

const API = import.meta.env.VITE_API_BASE_URL;

export const getSamples = () => axios.get(`${API}/sample-questions`).then((r) => r.data);
export const getHistory = () => axios.get(`${API}/submission-history`).then((r) => r.data);
export const addSample = (body) => axios.post(`${API}/add-sample-answer`, body).then((r) => r.data);
export const submitCode = (body) => axios.post(`${API}/submit-code`, body).then((r) => r.data);

// Turn an API error into a sentence a person can act on
export function errorMessage(err) {
  const detail = err?.response?.data?.detail || "";
  if (detail.includes("429") || detail.toLowerCase().includes("quota")) return "The AI's free daily limit has been reached. Please try again later.";
  if (!err?.response) return "Could not reach the server. It may be waking up, so please try again in a minute.";
  if (typeof detail === "string" && detail && detail.length < 160) return detail;
  return "Something went wrong. Please try again.";
}

export const titleCase = (s = "") => s.replace(/\b\w/g, (c) => c.toUpperCase());
export const fileName = (title = "", lang = "python") =>
  (title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "solution") + (lang === "python" ? ".py" : ".js");
