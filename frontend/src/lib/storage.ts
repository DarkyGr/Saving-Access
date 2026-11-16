/**
 * Per-device conveniences in localStorage (menu collapsed, groups closed).
 * Storage can be unavailable (private mode, blocked site data): reads fall
 * back to the default and writes are skipped. Nothing secret goes here.
 */
export function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeLocal(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Unavailable storage: the choice simply is not remembered.
  }
}
