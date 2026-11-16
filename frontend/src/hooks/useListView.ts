import { useEffect, useState } from "react";

import apiClient from "../api/apiClient";

export type ListKey = "credentials" | "users";
export type ListView = "list" | "grid";

/**
 * List or grid for one listing, saved in the account (Requirement 13.4):
 * read from `GET /api/profile/preferences`, saved with
 * `PUT /api/profile/preferences/list-view`. The screen shows *fallback*
 * until the saved choice arrives; a failed save keeps the local choice.
 */
export function useListView(key: ListKey, fallback: ListView): [ListView, (view: ListView) => void] {
  const [view, setView] = useState<ListView>(fallback);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve(apiClient.get<{ list_views: Partial<Record<ListKey, ListView>> }>("/api/profile/preferences"))
      .then((res) => {
        const saved = res.data?.list_views?.[key];
        if (!cancelled && (saved === "list" || saved === "grid")) setView(saved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [key]);

  function choose(next: ListView) {
    setView(next);
    Promise.resolve(apiClient.put("/api/profile/preferences/list-view", { key, view: next })).catch(() => undefined);
  }

  return [view, choose];
}
