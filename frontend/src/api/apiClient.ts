import axios from "axios";

/**
 * Shared Axios instance.
 *
 * - Base URL is read from the Vite env var VITE_API_URL (set in .env or
 *   docker-compose). Falls back to an empty string so relative paths work
 *   during local development proxied by Vite.
 * - A request interceptor injects `Authorization: Bearer <token>` from the
 *   in-memory token store.
 * - A response interceptor turns an expired-session 401 into one silent
 *   refresh + retry, and sends the browser to /login if that fails.
 */

const apiClient = axios.create({
  baseURL: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
  headers: { "Content-Type": "application/json" },
  // Needed so the browser stores / sends the httpOnly refresh cookie on
  // /api/auth/* (login, refresh, logout). The cookie's Path keeps it off
  // every other endpoint.
  withCredentials: true,
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

// Detail string the backend returns when the re-entered account password is
// wrong (design.md › Error Handling). Kept in one place so pages can share it.
export const ACCOUNT_PASSWORD_ERROR = "Account password verification failed.";

export function isAccountPasswordError(data: unknown): boolean {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { detail?: unknown }).detail === ACCOUNT_PASSWORD_ERROR
  );
}

// ── Session refresh (task 31.5) ──────────────────────────────────────────────
// The refresh token lives in an httpOnly cookie scoped to /api/auth; JS never
// sees it. These requests use a bare axios call so they skip the interceptors.

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

let refreshInFlight: Promise<string | null> | null = null;
let onTokenRefreshed: ((token: string) => void) | null = null;
let onSessionExpired: (() => void) | null = null;

/** AuthContext registers how to store a refreshed token and how to log out. */
export function registerSessionHandlers(handlers: {
  onTokenRefreshed: (token: string) => void;
  onSessionExpired: () => void;
}): void {
  onTokenRefreshed = handlers.onTokenRefreshed;
  onSessionExpired = handlers.onSessionExpired;
}

/**
 * Exchange the refresh cookie for a new access token. Concurrent callers
 * share one request (rotation would otherwise invalidate the second one).
 * Resolves to null when there is no valid session.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post<{ access_token: string }>(`${baseURL}/api/auth/refresh`, null, {
        withCredentials: true,
      })
      .then((res) => res.data.access_token)
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Revoke the refresh cookie server-side. Never throws. */
export async function revokeSession(): Promise<void> {
  try {
    await axios.post(`${baseURL}/api/auth/logout`, null, { withCredentials: true });
  } catch {
    // Logging out locally is enough if the server is unreachable.
  }
}

// ── Response interceptor: 401 → try one refresh, else back to login ─────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (
      !axios.isAxiosError(error) ||
      error.response?.status !== 401 ||
      // A wrong *account* password in the confirmation modal is a user typo,
      // not an expired session: let the page show its inline error.
      isAccountPasswordError(error.response?.data) ||
      // Login / register / refresh report their own 401s.
      (error.config?.url ?? "").startsWith("/api/auth/")
    ) {
      return Promise.reject(error);
    }

    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    if (original && !original._retried) {
      original._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        setAuthToken(token);
        onTokenRefreshed?.(token);
        original.headers.Authorization = `Bearer ${token}`;
        return apiClient(original);
      }
    }

    onSessionExpired?.();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
