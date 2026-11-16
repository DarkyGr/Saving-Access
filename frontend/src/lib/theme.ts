import { readLocal, writeLocal } from "./storage";

export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];
export const ACCENTS = ["indigo", "blue", "emerald", "violet", "rose", "amber"] as const;
export type Accent = (typeof ACCENTS)[number];

const THEME_KEY = "savepass-theme";
const ACCENT_KEY = "savepass-accent";

let mediaListener: ((e: MediaQueryListEvent) => void) | null = null;

/**
 * Apply theme and accent to <html> (task 37.3) and remember them on this
 * device, so public/theme-init.js paints the next load correctly before the
 * account's preferences arrive. "system" follows the OS while it changes.
 */
export function applyTheme(theme: Theme, accent: Accent): void {
  const root = document.documentElement;
  const media = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  root.classList.toggle("dark", theme === "dark" || (theme === "system" && !!media?.matches));
  root.dataset.accent = accent;
  writeLocal(THEME_KEY, theme);
  writeLocal(ACCENT_KEY, accent);

  if (media && mediaListener) media.removeEventListener?.("change", mediaListener);
  mediaListener = null;
  if (media && theme === "system") {
    mediaListener = (e) => root.classList.toggle("dark", e.matches);
    media.addEventListener?.("change", mediaListener);
  }
}

export function savedTheme(): { theme: Theme; accent: Accent } {
  const theme = readLocal<string>(THEME_KEY, "system");
  const accent = readLocal<string>(ACCENT_KEY, "indigo");
  return {
    theme: (THEMES as readonly string[]).includes(theme) ? (theme as Theme) : "system",
    accent: (ACCENTS as readonly string[]).includes(accent) ? (accent as Accent) : "indigo",
  };
}
