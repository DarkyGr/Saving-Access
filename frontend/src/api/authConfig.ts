import apiClient from "./apiClient";

/** Public settings from GET /api/auth/config (spec Phase 2, task 33). */
export interface AuthConfig {
  /** hCaptcha site key, or null when CAPTCHA is off. */
  captcha_site_key: string | null;
  /** Whether new accounts must verify their email. */
  email_verification: boolean;
}

const DISABLED: AuthConfig = { captcha_site_key: null, email_verification: false };

let cached: Promise<AuthConfig> | null = null;

/**
 * Fetch the config once per page load. A failed request falls back to
 * "everything off" for the UI; the backend still enforces its own settings,
 * so a missing CAPTCHA widget only means the login is rejected with a clear
 * message.
 */
export function getAuthConfig(): Promise<AuthConfig> {
  if (!cached) {
    cached = apiClient
      .get<AuthConfig>("/api/auth/config")
      .then((res) => ({ ...DISABLED, ...res.data }))
      .catch(() => {
        cached = null; // retry on the next call
        return DISABLED;
      });
  }
  return cached;
}

/** Test helper: forget the cached config. */
export function resetAuthConfigCache(): void {
  cached = null;
}
