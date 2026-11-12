import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useVisibilityTimer } from "../useVisibilityTimer";

// Requirements 5.7, 5.8, 5.9

describe("useVisibilityTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ── startTimer sets initial state ─────────────────────────────────────────

  it("isVisible is false and secondsRemaining is 0 before startTimer is called", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    expect(result.current.isVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(0);
  });

  it("isVisible becomes true immediately after startTimer() is called", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    expect(result.current.isVisible).toBe(true);
    expect(result.current.secondsRemaining).toBe(60);
  });

  // ── Auto-hide after 60 s (Requirement 5.7, 5.8) ───────────────────────────

  it("isVisible becomes false and secondsRemaining reaches 0 after 60 s (Requirement 5.7, 5.8)", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(result.current.isVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(0);
  });

  // ── secondsRemaining decrements correctly ─────────────────────────────────

  it("secondsRemaining decrements to ~50 after 10 s", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(result.current.secondsRemaining).toBe(50);
    expect(result.current.isVisible).toBe(true);
  });

  it("secondsRemaining decrements by 1 each second", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    for (let elapsed = 1; elapsed <= 5; elapsed++) {
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      expect(result.current.secondsRemaining).toBe(60 - elapsed);
    }
  });

  // ── Manual stopTimer halts countdown immediately (Requirement 5.9) ────────

  it("stopTimer() makes isVisible false immediately before 60 s elapse (Requirement 5.9)", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    // Advance part-way through the countdown
    act(() => {
      vi.advanceTimersByTime(20_000);
    });

    expect(result.current.isVisible).toBe(true);

    act(() => {
      result.current.stopTimer();
    });

    expect(result.current.isVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(0);
  });

  it("stopTimer() halts the countdown — no further decrement after stop", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    act(() => {
      result.current.stopTimer();
    });

    // Advance an additional 30 s — counter should stay at 0, not go negative
    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(result.current.isVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(0);
  });

  // ── Custom duration ───────────────────────────────────────────────────────

  it("respects a custom durationMs — auto-hides after the specified duration", () => {
    const { result } = renderHook(() => useVisibilityTimer(10_000));

    act(() => {
      result.current.startTimer();
    });

    expect(result.current.secondsRemaining).toBe(10);

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(result.current.isVisible).toBe(false);
    expect(result.current.secondsRemaining).toBe(0);
  });

  // ── Restart resets the countdown ─────────────────────────────────────────

  it("calling startTimer() again resets the countdown from the beginning", () => {
    const { result } = renderHook(() => useVisibilityTimer());

    act(() => {
      result.current.startTimer();
    });

    act(() => {
      vi.advanceTimersByTime(30_000); // halfway
    });

    expect(result.current.secondsRemaining).toBe(30);

    // Restart
    act(() => {
      result.current.startTimer();
    });

    expect(result.current.secondsRemaining).toBe(60);
    expect(result.current.isVisible).toBe(true);

    // Full 60 s from restart should auto-hide
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(result.current.isVisible).toBe(false);
  });
});
