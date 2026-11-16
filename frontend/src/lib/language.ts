/**
 * The language the person picked in this browser session (task 37.3).
 *
 * It wins over the copy saved in the account when the page loads, so a reload
 * right after switching never brings back the previous language; the account
 * copy is then brought up to date.
 */
const KEY = "savepass-language-chosen";

export function markLanguageChosen(lang: "en" | "es"): void {
  try {
    window.sessionStorage.setItem(KEY, lang);
  } catch {
    // Unavailable storage: the account copy decides on the next load.
  }
}

export function chosenLanguage(): "en" | "es" | null {
  try {
    const value = window.sessionStorage.getItem(KEY);
    return value === "en" || value === "es" ? value : null;
  } catch {
    return null;
  }
}
