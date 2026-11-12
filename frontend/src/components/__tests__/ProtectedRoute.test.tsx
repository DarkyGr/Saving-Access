import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ProtectedRoute, {
  setAuthStateForProtectedRoute,
} from "../ProtectedRoute";

// ── JWT helpers ──────────────────────────────────────────────────────────────

/**
 * Build a structurally-valid JWT (3-part base64url) for testing.
 * The signature is a stub — it is never verified on the client side.
 */
function makeTestJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
  const body = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
  return `${header}.${body}.fakesig`;
}

const FAR_FUTURE = Math.floor(Date.now() / 1000) + 86400; // +24 h

const USER_JWT = makeTestJwt({
  user_id: 1,
  username: "alice",
  role: "User",
  exp: FAR_FUTURE,
});

const ADMIN_JWT = makeTestJwt({
  user_id: 2,
  username: "admin",
  role: "Admin",
  exp: FAR_FUTURE,
});

// ── Test scaffold ────────────────────────────────────────────────────────────

/**
 * Wraps ProtectedRoute in a MemoryRouter and adds sentinel routes for /login
 * and /403 so we can assert redirects by the rendered text.
 */
function renderProtectedRoute(screen_key: string) {
  return render(
    <MemoryRouter initialEntries={["/protected"]}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route path="/403" element={<div>Forbidden Page</div>} />
        <Route
          path="/protected"
          element={
            <ProtectedRoute screen={screen_key}>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("ProtectedRoute", () => {
  beforeEach(() => {
    // Reset auth state before each test
    setAuthStateForProtectedRoute({ token: null, user: null });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    // Clean up global fetch stub
    vi.restoreAllMocks();
  });

  // ── 1. No token → redirect to /login ──────────────────────────────────────

  it("redirects to /login when token is null (Requirement 3.4)", async () => {
    // Auth state is already null from beforeEach
    renderProtectedRoute("credentials");

    await waitFor(() => {
      expect(screen.getByText("Login Page")).toBeInTheDocument();
    });

    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.queryByText("Forbidden Page")).not.toBeInTheDocument();
  });

  // ── 2. User JWT + missing permission → redirect to /403 ───────────────────

  it(
    "redirects to /403 when User lacks the required screen permission (Requirement 3.6)",
    async () => {
      setAuthStateForProtectedRoute({
        token: USER_JWT,
        user: { role: "User", user_id: 1 },
      });

      // Permissions API returns a list that does NOT include the requested screen
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ permissions: ["other-screen", "dashboard"] }),
        })
      );

      renderProtectedRoute("credentials");

      await waitFor(() => {
        expect(screen.getByText("Forbidden Page")).toBeInTheDocument();
      });

      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
      expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
    }
  );

  // ── 3. Admin JWT → renders children without a permissions check ────────────

  it(
    "renders children for Admin role without checking permissions (Requirement 3.4, 3.6)",
    async () => {
      setAuthStateForProtectedRoute({
        token: ADMIN_JWT,
        user: { role: "Admin", user_id: 2 },
      });

      // fetch should NOT be called for Admin
      const fetchSpy = vi.fn();
      vi.stubGlobal("fetch", fetchSpy);

      renderProtectedRoute("credentials");

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      expect(fetchSpy).not.toHaveBeenCalled();
      expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
      expect(screen.queryByText("Forbidden Page")).not.toBeInTheDocument();
    }
  );

  // ── 4. User JWT + matching permission → renders children ──────────────────

  it("renders children for User with a matching screen permission", async () => {
    setAuthStateForProtectedRoute({
      token: USER_JWT,
      user: { role: "User", user_id: 1 },
    });

    // Permissions API returns a list that DOES include the requested screen
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ permissions: ["credentials", "dashboard"] }),
      })
    );

    renderProtectedRoute("credentials");

    await waitFor(() => {
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });

    expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
    expect(screen.queryByText("Forbidden Page")).not.toBeInTheDocument();
  });

  // ── 5. Permissions API failure → redirect to /403 ─────────────────────────

  it("redirects to /403 when the permissions API call fails", async () => {
    setAuthStateForProtectedRoute({
      token: USER_JWT,
      user: { role: "User", user_id: 1 },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Unauthorized" }),
      })
    );

    renderProtectedRoute("credentials");

    await waitFor(() => {
      expect(screen.getByText("Forbidden Page")).toBeInTheDocument();
    });

    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });
});
