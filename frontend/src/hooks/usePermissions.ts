import { useEffect, useState } from "react";

import apiClient from "../api/apiClient";

/**
 * The signed-in user's permissions from `GET /api/profile/permissions`
 * (task 37.1: an explicit list for every role). Empty while signed out, while
 * loading or when the request fails — deny by default.
 *
 * `role` is only a dependency: a new token with another role refetches.
 */
export function usePermissions(token: string | null, role: string | undefined): string[] {
  const [permissions, setPermissions] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setPermissions([]);
      return;
    }
    apiClient
      .get<{ permissions: string[] }>("/api/profile/permissions")
      .then((res) => {
        if (!cancelled) setPermissions(res.data.permissions ?? []);
      })
      .catch(() => {
        if (!cancelled) setPermissions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, role]);

  return permissions;
}
