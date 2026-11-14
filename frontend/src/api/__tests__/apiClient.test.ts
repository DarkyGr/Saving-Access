import { describe, it, expect } from "vitest";
import { ACCOUNT_PASSWORD_ERROR, isAccountPasswordError } from "../apiClient";

describe("isAccountPasswordError", () => {
  it("matches the backend's wrong-account-password detail", () => {
    // Must stay identical to the detail asserted in
    // backend/tests/test_mvp_contract.py.
    expect(ACCOUNT_PASSWORD_ERROR).toBe("Account password verification failed.");
    expect(isAccountPasswordError({ detail: ACCOUNT_PASSWORD_ERROR })).toBe(true);
  });

  it("does not match an expired or invalid session", () => {
    expect(isAccountPasswordError({ detail: "Token expired." })).toBe(false);
    expect(isAccountPasswordError({ detail: "Not authenticated." })).toBe(false);
    expect(isAccountPasswordError(undefined)).toBe(false);
    expect(isAccountPasswordError("Account password verification failed.")).toBe(false);
  });
});

// ── Silent refresh (task 31.5) ───────────────────────────────────────────────

import { vi, beforeEach, afterEach } from "vitest";
import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import apiClient, { registerSessionHandlers, setAuthToken } from "../apiClient";

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown) {
  const response = { data, status, statusText: String(status), headers: {}, config };
  if (status >= 400) {
    return Promise.reject(new AxiosError("fail", String(status), config, null, response));
  }
  return Promise.resolve(response);
}

describe("apiClient 401 handling", () => {
  const originalAdapter = apiClient.defaults.adapter;
  const onTokenRefreshed = vi.fn();
  const onSessionExpired = vi.fn();

  beforeEach(() => {
    onTokenRefreshed.mockReset();
    onSessionExpired.mockReset();
    registerSessionHandlers({ onTokenRefreshed, onSessionExpired });
    setAuthToken("old-token");
    window.history.pushState({}, "", "/credentials");
  });

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
    setAuthToken(null);
  });

  it("refreshes once and retries the request with the new token", async () => {
    const seen: (string | undefined)[] = [];
    const adapter: AxiosAdapter = (config) => {
      seen.push(config.headers.Authorization as string | undefined);
      return seen.length === 1
        ? respond(config, 401, { detail: "Token expired." })
        : respond(config, 200, [{ credential_id: 1 }]);
    };
    apiClient.defaults.adapter = adapter;
    const post = vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "new-token" } });

    const res = await apiClient.get("/api/credentials");

    expect(res.data).toEqual([{ credential_id: 1 }]);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatch(/\/api\/auth\/refresh$/);
    expect(seen).toEqual(["Bearer old-token", "Bearer new-token"]);
    expect(onTokenRefreshed).toHaveBeenCalledWith("new-token");
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it("clears the session when the refresh cookie is no longer valid", async () => {
    apiClient.defaults.adapter = (config) => respond(config, 401, { detail: "Token expired." });
    vi.spyOn(axios, "post").mockRejectedValue(new Error("401"));

    await expect(apiClient.get("/api/credentials")).rejects.toBeTruthy();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it("does not refresh on a wrong account password", async () => {
    apiClient.defaults.adapter = (config) =>
      respond(config, 401, { detail: ACCOUNT_PASSWORD_ERROR });
    const post = vi.spyOn(axios, "post");

    await expect(apiClient.post("/api/credentials/1/reveal", {})).rejects.toBeTruthy();
    expect(post).not.toHaveBeenCalled();
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it("does not refresh on a failed login", async () => {
    apiClient.defaults.adapter = (config) =>
      respond(config, 401, { detail: "Invalid credentials." });
    const post = vi.spyOn(axios, "post");

    await expect(apiClient.post("/api/auth/login", {})).rejects.toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });
});
