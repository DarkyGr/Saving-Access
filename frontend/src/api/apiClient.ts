import axios from "axios";

/**
 * Shared Axios instance.
 *
 * - Base URL is read from the Vite env var VITE_API_URL (set in .env or
 *   docker-compose). Falls back to an empty string so relative paths work
 *   during local development proxied by Vite.
 * - A request interceptor injects `Authorization: Bearer <token>` from the
 *   in-memory token store.
 * - A response interceptor redirects the browser to /login on any 401.
 */

const apiClient = axios.create({
  baseURL: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
  headers: { "Content-Type": "application/json" },
});

// ── In-memory token store ────────────────────────────────────────────────────
// The token is held here (module-level variable) and NEVER written to
// localStorage, sessionStorage, or cookies (Requirement 8.3).
let _token: string | null = null;

/**
 * Update the stored token. Called by AuthContext on login/logout so that the
 * axios interceptor always has the latest value without needing React context.
 */
export function setAuthToken(token: string | null): void {
  _token = token;
}

// ── Request interceptor: attach Bearer token ─────────────────────────────────
apiClient.interceptors.request.use((config) => {
  if (_token) {
    config.headers.Authorization = `Bearer ${_token}`;
  }
  return config;
});

// ── Response interceptor: handle 401 → redirect to login ────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (
      axios.isAxiosError(error) &&
      error.response?.status === 401 &&
      // Avoid redirect loops on the login page itself
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
