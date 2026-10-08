import { useState, useRef, useCallback } from "react";

export interface UseVisibilityTimerResult {
  /** Whether the password is currently visible */
  isVisible: boolean;
  /** Seconds remaining before auto-hide (0 when not active) */
  secondsRemaining: number;
  /** Start or restart the visibility timer and mark password as visible */
  startTimer: () => void;
  /** Stop the timer immediately and mark password as hidden */
  stopTimer: () => void;
}

/**
 * Custom hook that manages a countdown timer for password visibility.
 *
 * - Uses `useRef` for the interval ID to avoid stale-closure issues.
 * - Calling `startTimer()` always resets any existing interval before starting fresh.
 * - When `secondsRemaining` reaches 0, `stopTimer()` is called automatically.
 *
 * @param durationMs  Total visibility duration in milliseconds (default: 60 000)
 */
export function useVisibilityTimer(durationMs = 60_000): UseVisibilityTimerResult {
  const totalSeconds = Math.ceil(durationMs / 1_000);

  const [isVisible, setIsVisible] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(0);

  // Store interval ID in a ref so callbacks always see the latest value
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearExistingInterval = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const stopTimer = useCallback(() => {
    clearExistingInterval();
    setIsVisible(false);
    setSecondsRemaining(0);
  }, [clearExistingInterval]);

  const startTimer = useCallback(() => {
    // Reset any running interval first
    clearExistingInterval();

    setIsVisible(true);
    setSecondsRemaining(totalSeconds);

    // Capture a mutable counter in the closure via a local variable; the
    // ref is used only for cleanup, so there are no stale-closure issues
    // with the counter itself.
    let remaining = totalSeconds;

    intervalRef.current = setInterval(() => {
      remaining -= 1;
      setSecondsRemaining(remaining);

      if (remaining <= 0) {
        clearExistingInterval();
        setIsVisible(false);
        setSecondsRemaining(0);
      }
    }, 1_000);
  }, [totalSeconds, clearExistingInterval]);

  return { isVisible, secondsRemaining, startTimer, stopTimer };
}
