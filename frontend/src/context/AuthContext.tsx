import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { setAuthToken } from "../api/apiClient";
import { setAuthStateForProtectedRoute } from "../components/ProtectedRoute";

// ── Types ────────────────────────────────────────────────────────────────────

/** Shape of the claims we read from the JWT payload. */
export interface JwtUser {
  user_id: number;
  username: string;
  role: "User" | "Admin";
}

export interface AuthContextValue {
  /** Raw JWT string, or null when logged out. Stored in React state only — never localStorage. */
  token: string | null;
  /** Decoded user claims derived from the JWT, or null when logged out. */
  user: JwtUser | null;
  /** Persist a new JWT (called after a successful login). */
  login: (token: string) => void;
  /** Clear all auth state (called on explicit logout or on 401). */
  logout: () => void;
}

// ── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ── JWT decode helper ────────────────────────────────────────────────────────

/**
 * Decode the payload segment of a JWT without verifying its signature.
 * The server is the authority on validity; we only read claims client-side
 * to drive UI decisions (role, user_id).
 *
 * Returns null if the token is structurally invalid.
 */
function decodeJwtPayload(token: string): JwtUser | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    // Base64url → Base64 → JSON
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    // Pad to a multiple of 4 so atob never throws
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "="
    );
    const json = atob(padded);
    const payload = JSON.parse(json) as Record<string, unknown>;

    const user_id = payload["user_id"];
    const username = payload["username"];
    const role = payload["role"];

    if (
      typeof user_id !== "number" ||
      typeof username !== "string" ||
      (role !== "User" && role !== "Admin")
    ) {
      return null;
    }

    return { user_id, username, role };
  } catch {
    return null;
  }
}

// ── Provider ─────────────────────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider holds auth state entirely in React memory.
 *
 * Security guarantees (Requirement 8.3):
 * - `token` lives only in useState — never written to localStorage,
 *   sessionStorage, or cookies.
 * - On page refresh the user is logged out (re-authentication required).
 *
 * Integration:
 * - Calls `setAuthToken` so the axios interceptor always has the current token.
 * - Calls `setAuthStateForProtectedRoute` so ProtectedRoute can read the
 *   current auth state synchronously without a separate hook call.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<JwtUser | null>(null);

  const login = useCallback((newToken: string) => {
    const decoded = decodeJwtPayload(newToken);
    // If the token is structurally invalid we refuse to store it
    if (!decoded) {
      console.error("AuthContext.login: received a malformed JWT — ignoring.");
      return;
    }

    setToken(newToken);
    setUser(decoded);

    // Keep axios interceptor in sync
    setAuthToken(newToken);

    // Keep ProtectedRoute's module-level cache in sync
    setAuthStateForProtectedRoute({ token: newToken, user: decoded });
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);

    // Clear axios interceptor token
    setAuthToken(null);

    // Clear ProtectedRoute cache
    setAuthStateForProtectedRoute({ token: null, user: null });
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * useAuth — returns the current auth context value.
 *
 * Must be used inside an <AuthProvider>. Throws a clear error otherwise so
 * misuse is caught early during development.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an <AuthProvider>.");
  }
  return ctx;
}
