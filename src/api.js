// Set VITE_API_URL only when the frontend and API are hosted separately.
// Locally, leave it unset so Vite's /api proxy sends requests to localhost:8000.
const configuredApiUrl = (import.meta.env.VITE_API_URL || "").trim();
const API_ORIGIN = configuredApiUrl
  ? (configuredApiUrl.startsWith("http")
      ? configuredApiUrl
      : `https://${configuredApiUrl}`).replace(/\/+$/, "")
  : "";
const API_URL = `${API_ORIGIN}/api`;

export async function api(path, options = {}) {
  const token = localStorage.getItem("token");
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new Error("Could not connect to the server. Check that the API is running.");
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.dispatchEvent(new Event("auth-expired"));
    }
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    const error = new Error(payload.error || detail || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const jsonBody = (value) => JSON.stringify(value);

export function currentUser() {
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    return null;
  }
}

export function storeSession(session) {
  localStorage.setItem("token", session.token);
  localStorage.setItem("user", JSON.stringify(session.user));
}

export function logout(navigate) {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.dispatchEvent(new Event("auth-logged-out"));
  navigate("/login", { replace: true });
}
