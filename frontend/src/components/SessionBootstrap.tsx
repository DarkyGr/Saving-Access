import { useEffect, useState, type ReactNode } from "react";
import { refreshAccessToken } from "../api/apiClient";
import { useAuth } from "../context/AuthContext";

/**
 * Restores the session after a page reload (task 31.5).
 *
 * The access token only lives in memory, so a reload loses it. Before the
 * routes render, try the httpOnly refresh cookie once; if it is valid the
 * user stays signed in, otherwise ProtectedRoute sends them to /login.
 */
export default function SessionBootstrap({ children }: { children: ReactNode }) {
  const { login } = useAuth();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    refreshAccessToken().then((token) => {
      if (cancelled) return;
      if (token) login(token);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [login]);

  if (!ready) return null;
  return <>{children}</>;
}
