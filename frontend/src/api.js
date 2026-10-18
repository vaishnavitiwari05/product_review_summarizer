// Thin client for the FastAPI backend. Every failure becomes an ApiError with a
// user-friendly message, so components never deal with raw fetch errors.

// VITE_API_URL="" means "same origin" (used behind the dev proxy / nginx, so no CORS is involved).
export const API_URL = (import.meta.env?.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(code, message, status = 0, details = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new ApiError(
      "network",
      `Cannot reach the analysis server${API_URL ? ` at ${API_URL}` : ""}. Make sure the backend is running.`
    );
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON response */
  }
  if (!res.ok) {
    throw new ApiError(
      body?.error || "http_error",
      body?.message || `The server returned an error (HTTP ${res.status}).`,
      res.status,
      body?.details || {}
    );
  }
  return body;
}

const json = (data) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  health: () => request("/health"),
  products: () => request("/products").then((r) => r.products),
  uploadCsv: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/upload", { method: "POST", body: form });
  },
  loadSample: () => request("/sample", { method: "POST" }),
  startAnalysis: (productId) => request("/analyze", json({ product_id: productId })),
  runStatus: (runId) => request(`/analyze/${runId}`),
  results: (productId) => request(`/results/${encodeURIComponent(productId)}`),
};
