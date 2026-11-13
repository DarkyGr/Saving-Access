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
