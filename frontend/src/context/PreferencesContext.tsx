import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import i18n from "i18next";

import apiClient from "../api/apiClient";
import { useAuth } from "./AuthContext";
import { applyTheme, type Accent, type Theme } from "../lib/theme";
import { chosenLanguage } from "../lib/language";

export type StartPage = "home" | "credentials" | "credentials-new";

export interface Preferences {
  list_views: Record<string, "list" | "grid">;
  theme: Theme;
  accent: Accent;
  start_page: StartPage;
  private_mode: boolean;
  language: "en" | "es" | null;
  avatar_preset: string | null;
  has_avatar_image: boolean;
}

export interface Me {
  user_id: number;
  user_code: string;
  username: string;
  display_name: string | null;
  email: string;
  role: "User" | "Admin";
  email_verified: boolean;
  preferences: Preferences;
}

export const DEFAULT_PREFERENCES: Preferences = {
  list_views: {},
  theme: "system",
  accent: "indigo",
  start_page: "home",
  private_mode: false,
  language: null,
  avatar_preset: null,
  has_avatar_image: false,
};

export const START_PATHS: Record<StartPage, string> = {
  home: "/",
  credentials: "/credentials",
  "credentials-new": "/credentials/new",
};

interface PreferencesValue {
  me: Me | null;
  prefs: Preferences;
  /** Object URL of the uploaded picture, or null. */
  avatarUrl: string | null;
  updatePreferences: (changes: Partial<Omit<Preferences, "list_views" | "avatar_preset" | "has_avatar_image">>) => Promise<void>;
  setDisplayName: (name: string) => Promise<void>;
  setAvatarPreset: (preset: string) => Promise<void>;
  uploadAvatar: (picture: Blob) => Promise<void>;
  clearAvatar: () => Promise<void>;
}

const noop = async () => undefined;

// Screens rendered outside the provider (unit tests) get safe defaults.
const PreferencesContext = createContext<PreferencesValue>({
  me: null,
  prefs: DEFAULT_PREFERENCES,
  avatarUrl: null,
  updatePreferences: noop,
  setDisplayName: noop,
  setAvatarPreset: noop,
  uploadAvatar: noop,
  clearAvatar: noop,
});

/**
 * The signed-in account and its preferences (Requirement 14, task 37.3),
 * loaded after sign-in and applied everywhere: theme and accent on <html>,
 * the interface language, private mode and the avatar.
 */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const { token, user } = useAuth();
  const userId = token ? user?.user_id ?? null : null;
  const [me, setMe] = useState<Me | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const prefs = me?.preferences ?? DEFAULT_PREFERENCES;

  const adopt = useCallback((next: Me) => {
    const chosen = chosenLanguage();
    if (chosen && chosen !== next.preferences.language) {
      // Picked in this browser session: it wins, and the account follows.
      setMe({ ...next, preferences: { ...next.preferences, language: chosen } });
      if (!i18n.language?.startsWith(chosen)) void i18n.changeLanguage(chosen);
      void Promise.resolve(apiClient.put("/api/profile/preferences", { language: chosen })).catch(() => undefined);
      return;
    }
    setMe(next);
    if (next.preferences.language && !i18n.language?.startsWith(next.preferences.language)) {
      void i18n.changeLanguage(next.preferences.language);
    }
  }, []);

  const setPrefs = useCallback((p: Preferences) => {
    setMe((current) => (current ? { ...current, preferences: p } : current));
  }, []);

  // Theme and accent follow the account while signed in (applyTheme also
  // remembers them on this device for the next first paint).
  const signedIn = me !== null;
  useEffect(() => {
    if (signedIn) applyTheme(prefs.theme, prefs.accent);
  }, [signedIn, prefs.theme, prefs.accent]);

  useEffect(() => {
    let cancelled = false;
    if (userId === null) {
      setMe(null);
      return;
    }
    Promise.resolve(apiClient.get<Me>("/api/profile/me"))
      .then((res) => {
        if (!cancelled && res?.data?.user_code) adopt(res.data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Keyed on the account, not the token: a silent refresh does not reload it.
  }, [userId, adopt]);

  // The uploaded picture is fetched with the token (an <img src> cannot send it).
  const hasImage = prefs.has_avatar_image;
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    if (userId === null || !hasImage) {
      setAvatarUrl(null);
      return;
    }
    Promise.resolve(apiClient.get<Blob>("/api/profile/avatar/image", { responseType: "blob" }))
      .then((res) => {
        if (cancelled || !res?.data) return;
        url = URL.createObjectURL(res.data);
        setAvatarUrl(url);
      })
      .catch(() => setAvatarUrl(null));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [userId, hasImage, avatarVersion]);

  const value = useMemo<PreferencesValue>(
    () => ({
      me,
      prefs,
      avatarUrl,
      updatePreferences: (changes) => {
        // Optimistic: the screen follows at once (theme, accent, private mode).
        setMe((current) => (current ? { ...current, preferences: { ...current.preferences, ...changes } } : current));
        // One save at a time, in the order they were made: two quick changes
        // (EN then ES) must not reach the server, or come back, out of order.
        const job = queue.current.then(async () => {
          const res = await apiClient.put<Preferences>("/api/profile/preferences", changes);
          setPrefs(res.data);
        });
        queue.current = job.catch(() => undefined);
        return job;
      },
      setDisplayName: async (name) => {
        const res = await apiClient.put<Me>("/api/profile/me", { display_name: name });
        setMe(res.data);
      },
      setAvatarPreset: async (preset) => {
        const res = await apiClient.put<Preferences>("/api/profile/avatar/preset", { preset });
        setPrefs(res.data);
      },
      uploadAvatar: async (picture) => {
        const res = await apiClient.put<Preferences>("/api/profile/avatar/image", picture, {
          headers: { "Content-Type": picture.type || "image/webp" },
        });
        setPrefs(res.data);
        setAvatarVersion((v) => v + 1);
      },
      clearAvatar: async () => {
        const res = await apiClient.delete<Preferences>("/api/profile/avatar");
        setPrefs(res.data);
      },
    }),
    [me, prefs, avatarUrl, setPrefs]
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  return useContext(PreferencesContext);
}

/** Private mode (Requirement 14.3): usernames and emails shown as dots. */
export function usePrivacy() {
  const { prefs, updatePreferences } = usePreferences();
  const hidden = prefs.private_mode;
  return {
    hidden,
    toggle: () => updatePreferences({ private_mode: !hidden }),
    mask: (text: string) => (hidden ? "••••••••" : text),
  };
}
