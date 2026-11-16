import { JSX, useEffect, useState } from "react";
import { Navigate } from "react-router";

// ──────────────────────────────────────────────────────────────────────────────
// AuthContext stub — will be fulfilled by the real module in task 17.2.
// We import via a lazy dynamic import so the file compiles even before
// AuthContext exists. The hook is typed here to keep strict mode happy.
// ──────────────────────────────────────────────────────────────────────────────

interface AuthState {
  token: string | null;
  user: { role: "Admin" | "User"; user_id: number } | null;
}

// Module-level cache so we only attempt the import once per session.
let _authState: AuthState = { token: null, user: null };

/**
 * Call this from AuthContext once it is created (task 17.2) to wire up the
 * real auth state. Until then ProtectedRoute redirects every request to /login.
 */
export function setAuthStateForProtectedRoute(state: AuthState) {
  _authState = state;
}

// ──────────────────────────────────────────────────────────────────────────────

/**
 * Decode the payload of a JWT without verifying its signature.
 * Returns the decoded object or null if the token is malformed.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Base64url → Base64 → JSON
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

// ──────────────────────────────────────────────────────────────────────────────

export interface ProtectedRouteProps {
  /** The permission the route needs, e.g. "credentials.view" (task 37.1) */
  permission: string;
  /** The component to render when access is granted */
  children: JSX.Element;
}

type Status = "loading" | "allowed" | "forbidden" | "unauthenticated";

/**
 * Higher-order component that protects a route.
 *
 * Logic:
 *  1. Read JWT from AuthContext in-memory state (never localStorage).
 *  2. Fetch `GET /api/profile/permissions` and check `permission` in the
 *     list — for every role, Admin included (no bypass, task 37.1).
 *  3. No token → redirect to `/login`.
 *  4. Permission denied → redirect to `/403`.
 *
 * NOTE: Once task 17.2 (AuthContext) is implemented, replace the `_authState`
 * module-level variable usage here with a `useAuth()` hook call.
 */
export default function ProtectedRoute({
  permission,
  children,
}: ProtectedRouteProps) {
  const [status, setStatus] = useState<Status>("loading");

  // Read auth state. After task 17.2 this will be a useAuth() hook call.
  const token = _authState.token;

  useEffect(() => {
    let cancelled = false;

    async function checkPermission() {
      if (!token) {
        setStatus("unauthenticated");
        return;
      }

      if (!decodeJwtPayload(token)) {
        setStatus("unauthenticated");
        return;
      }

      // The backend decides from the role stored now (no client-side bypass).
      try {
        const apiBase = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
        const res = await fetch(`${apiBase}/api/profile/permissions`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!cancelled) {
          if (!res.ok) {
            setStatus("forbidden");
            return;
          }
          const data = (await res.json()) as { permissions: string[] };
          const permissions: string[] = data.permissions ?? [];
          setStatus(permissions.includes(permission) ? "allowed" : "forbidden");
        }
      } catch {
        if (!cancelled) setStatus("forbidden");
      }
    }

    checkPermission();
    return () => {
      cancelled = true;
    };
  }, [token, permission]);

  if (status === "loading") {
    // Render nothing while the async permission check is in-flight
    return null;
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  if (status === "forbidden") {
    return <Navigate to="/403" replace />;
  }

  return children;
}
