/**
 * Copy a revealed password and clear the clipboard 30 seconds later if it
 * still holds that password (Requirement 16.6, task 37.5).
 *
 * Where the browser lets the page read the clipboard, the check is exact.
 * Where it does not, the clipboard is cleared only if nothing else was copied
 * on this page in the meantime, so the person's own copy is never wiped.
 */
export const CLEAR_AFTER_MS = 30_000;

let generation = 0;
let pendingTimer: number | undefined;

function noteOtherCopy() {
  generation += 1;
}

if (typeof document !== "undefined") {
  document.addEventListener("copy", noteOtherCopy);
}

async function clearIfStill(secret: string, mine: number): Promise<void> {
  try {
    if (navigator.clipboard?.readText) {
      const current = await navigator.clipboard.readText();
      if (current === secret) await navigator.clipboard.writeText("");
      return;
    }
  } catch {
    // Reading not allowed: fall back to "nothing else was copied here".
  }
  if (generation === mine) {
    try {
      await navigator.clipboard.writeText("");
    } catch {
      // The page lost focus or permission: nothing more can be done.
    }
  }
}

/** Copy *secret*; resolves to false when the browser refused. */
export async function copySecret(secret: string, clearAfterMs = CLEAR_AFTER_MS): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(secret);
  } catch {
    return false;
  }
  const mine = ++generation;
  window.clearTimeout(pendingTimer);
  pendingTimer = window.setTimeout(() => void clearIfStill(secret, mine), clearAfterMs);
  return true;
}

/** For a password copied by hand (Ctrl+C / long press) from the screen. */
export function clearLaterIfCopied(secret: string, clearAfterMs = CLEAR_AFTER_MS): void {
  // Called from the element's copy handler; this same copy event then
  // reaches the document listener, which moves the generation on by one.
  const mine = generation + 1;
  window.clearTimeout(pendingTimer);
  pendingTimer = window.setTimeout(() => void clearIfStill(secret, mine), clearAfterMs);
}
