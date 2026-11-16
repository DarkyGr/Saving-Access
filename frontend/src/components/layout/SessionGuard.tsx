import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import apiClient from "../../api/apiClient";
import { readLocal, writeLocal } from "../../lib/storage";

interface Limits {
  idle_seconds: number;
  expires_in_seconds: number | null;
  extend_minutes: number;
}

export type EndReason = "idle" | "max";

// Shared by every tab of this browser: activity in one keeps all open.
const ACTIVITY_KEY = "savepass-last-activity";
const PING_KEY = "savepass-last-ping";
const WARN_MS = 60_000;
const PING_EVERY_MS = 60_000;
const EVENTS = ["mousedown", "keydown", "touchstart", "scroll", "mousemove"] as const;

function sharedTime(key: string): number {
  const value = Number(readLocal<number>(key, 0));
  return Number.isFinite(value) ? value : 0;
}

/**
 * Session limits in the browser (Requirement 16.4, task 37.5): one minute
 * before the idle limit "Stay signed in", one minute before the maximum
 * "Extend N min"; at zero the session ends. Activity is reported to the API
 * at most once a minute, which keeps the server-side session open too.
 */
export default function SessionGuard({ onEnd }: { onEnd: (reason: EndReason) => void }) {
  const { t } = useTranslation();
  const [limits, setLimits] = useState<{ idleMs: number; deadline: number | null; extend: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const lastActivity = useRef(Date.now());
  const ended = useRef(false);

  const load = useCallback((data: Limits) => {
    setLimits({
      idleMs: data.idle_seconds * 1000,
      deadline: data.expires_in_seconds === null ? null : Date.now() + data.expires_in_seconds * 1000,
      extend: data.extend_minutes,
    });
  }, []);

  useEffect(() => {
    Promise.resolve(apiClient.get<Limits>("/api/profile/session"))
      .then((res) => res?.data && load(res.data))
      .catch(() => undefined);
  }, [load]);

  const ping = useCallback(() => {
    writeLocal(PING_KEY, Date.now());
    void Promise.resolve(apiClient.post("/api/profile/session/ping")).catch(() => undefined);
  }, []);

  const markActivity = useCallback(() => {
    const at = Date.now();
    if (at - lastActivity.current < 1000) return;
    lastActivity.current = at;
    writeLocal(ACTIVITY_KEY, at);
    if (at - sharedTime(PING_KEY) >= PING_EVERY_MS) ping();
  }, [ping]);

  useEffect(() => {
    lastActivity.current = Date.now();
    writeLocal(ACTIVITY_KEY, lastActivity.current);
    const onStorage = (e: StorageEvent) => {
      if (e.key === ACTIVITY_KEY && e.newValue) lastActivity.current = Math.max(lastActivity.current, Number(e.newValue));
    };
    EVENTS.forEach((name) => window.addEventListener(name, markActivity, { passive: true }));
    window.addEventListener("storage", onStorage);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      EVENTS.forEach((name) => window.removeEventListener(name, markActivity));
      window.removeEventListener("storage", onStorage);
      window.clearInterval(timer);
    };
  }, [markActivity]);

  const idleLeft = limits ? Math.max(lastActivity.current, sharedTime(ACTIVITY_KEY)) + limits.idleMs - now : Infinity;
  const maxLeft = limits?.deadline != null ? limits.deadline - now : Infinity;

  useEffect(() => {
    if (ended.current || !limits) return;
    if (maxLeft <= 0 || idleLeft <= 0) {
      ended.current = true;
      onEnd(maxLeft <= 0 ? "max" : "idle");
    }
  }, [idleLeft, maxLeft, limits, onEnd]);

  async function extend() {
    try {
      const res = await apiClient.post<Limits>("/api/profile/session/extend");
      load(res.data);
    } catch {
      // The session already ended: the next request sends the person to sign in.
    }
  }

  const warning: EndReason | null = maxLeft <= WARN_MS ? "max" : idleLeft <= WARN_MS ? "idle" : null;
  if (!warning || !limits) return null;
  const seconds = Math.max(0, Math.ceil((warning === "max" ? maxLeft : idleLeft) / 1000));

  return (
    <div
      role="alertdialog"
      aria-labelledby="session-warning-title"
      aria-describedby="session-warning-text"
      className="fixed bottom-4 right-4 z-50 w-[calc(100%-2rem)] max-w-sm rounded-lg border border-amber-300 bg-white p-4 shadow-xl"
    >
      <h2 id="session-warning-title" className="text-base font-semibold text-gray-900">
        {t("session.warningTitle")}
      </h2>
      <p id="session-warning-text" className="mt-1 text-sm text-gray-700" aria-live="polite">
        {warning === "idle" ? t("session.idleWarning", { seconds }) : t("session.maxWarning", { seconds })}
      </p>
      <button
        type="button"
        onClick={() => {
          if (warning === "idle") {
            lastActivity.current = Date.now();
            writeLocal(ACTIVITY_KEY, lastActivity.current);
            ping();
          } else {
            void extend();
          }
        }}
        className="mt-3 min-h-[44px] w-full rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700"
      >
        {warning === "idle" ? t("session.stay") : t("session.extend", { minutes: limits.extend })}
      </button>
    </div>
  );
}
