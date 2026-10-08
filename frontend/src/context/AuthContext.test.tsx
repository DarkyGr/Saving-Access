import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
import * as apiClient from "../api/apiClient";

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Build a minimal structurally-valid JWT with the given payload.
 * Signature segment is a dummy — we never verify it client-side.
 */
function makeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const body = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `${header}.${body}.fakesignature`;
}

const validUserToken = makeJwt({
  user_id: 42,
  username: "alice",
  role: "User",
  exp: Math.floor(Date.now() / 1000) + 900,
});

const validAdminToken = makeJwt({
  user_id: 1,
  username: "admin",
  role: "Admin",
  exp: Math.floor(Date.now() / 1000) + 900,
});

const malformedToken = "not.a.jwt.with.wrong.segments";

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

// ── Tests ────────────────────────────────────────────────────────────────────

describe("AuthContext", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // ── Initial state ──────────────────────────────────────────────────────────

  it("starts with token=null and user=null", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  // ── login() ───────────────────────────────────────────────────────────────

  it("login() sets token and decoded user for a User JWT", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });

    expect(result.current.token).toBe(validUserToken);
    expect(result.current.user).toEqual({
      user_id: 42,
      username: "alice",
      role: "User",
    });
  });

  it("login() sets token and decoded user for an Admin JWT", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validAdminToken);
    });

    expect(result.current.token).toBe(validAdminToken);
    expect(result.current.user).toEqual({
      user_id: 1,
      username: "admin",
      role: "Admin",
    });
  });

  it("login() calls setAuthToken with the new token", () => {
    const spy = vi.spyOn(apiClient, "setAuthToken");
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });

    expect(spy).toHaveBeenCalledWith(validUserToken);
  });

  it("login() ignores a malformed JWT and keeps state unchanged", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(malformedToken);
    });

    // State must stay null — no crash
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  // ── logout() ──────────────────────────────────────────────────────────────

  it("logout() clears token and user after login", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });
    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it("logout() calls setAuthToken(null)", () => {
    const spy = vi.spyOn(apiClient, "setAuthToken");
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });
    act(() => {
      result.current.logout();
    });

    // The last call must be with null
    expect(spy).toHaveBeenLastCalledWith(null);
  });

  // ── Token storage ─────────────────────────────────────────────────────────

  it("never writes token to localStorage (Requirement 8.3)", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });

    // localStorage.setItem must never have been called with our token
    const tokenWrites = setItemSpy.mock.calls.filter(([, value]) =>
      String(value).includes(validUserToken)
    );
    expect(tokenWrites).toHaveLength(0);
  });

  it("never writes token to sessionStorage (Requirement 8.3)", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login(validUserToken);
    });

    const tokenWrites = setItemSpy.mock.calls.filter(([, value]) =>
      String(value).includes(validUserToken)
    );
    expect(tokenWrites).toHaveLength(0);
  });

  // ── useAuth outside provider ───────────────────────────────────────────────

  it("useAuth() throws when used outside AuthProvider", () => {
    // Silence the expected React error boundary noise in test output
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within an <AuthProvider>."
    );

    consoleSpy.mockRestore();
  });

  // ── Multiple consumers see the same state ─────────────────────────────────

  it("multiple consumers of useAuth share the same token state", () => {
    const Consumer1 = () => {
      const { token } = useAuth();
      return <span data-testid="c1">{token ?? "null"}</span>;
    };
    const Consumer2 = () => {
      const { token } = useAuth();
      return <span data-testid="c2">{token ?? "null"}</span>;
    };
    const Trigger = () => {
      const { login } = useAuth();
      return (
        <button onClick={() => login(validUserToken)}>login</button>
      );
    };

    const { getByTestId, getByRole } = render(
      <AuthProvider>
        <Consumer1 />
        <Consumer2 />
        <Trigger />
      </AuthProvider>
    );

    act(() => {
      getByRole("button", { name: "login" }).click();
    });

    expect(getByTestId("c1").textContent).toBe(validUserToken);
    expect(getByTestId("c2").textContent).toBe(validUserToken);
  });
});
