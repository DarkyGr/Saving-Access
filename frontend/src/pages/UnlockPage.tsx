import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";

type Outcome = "ready" | "working" | "unlocked" | "invalid" | "error";

/**
 * UnlockPage — /unlock?token=… (Requirement 16.2, task 37.5).
 *
 * Opened from the lock email. The link is used only when the person presses
 * the button, so a mail scanner that opens it unlocks nothing.
 */
export default function UnlockPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [outcome, setOutcome] = useState<Outcome>(token ? "ready" : "invalid");

  async function unlock() {
    setOutcome("working");
    try {
      await apiClient.post("/api/auth/unlock", { token });
      setOutcome("unlocked");
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setOutcome(status === 400 || status === 422 ? "invalid" : "error");
    }
  }

  const message = {
    ready: t("unlock.ready"),
    working: t("common.loading"),
    unlocked: t("unlock.done"),
    invalid: t("unlock.invalid"),
    error: t("errors.generic"),
  }[outcome];
  const tone =
    outcome === "unlocked"
      ? "bg-green-50 text-green-800"
      : outcome === "invalid" || outcome === "error"
        ? "bg-red-50 text-red-700"
        : "text-gray-600";

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl bg-white px-8 py-10 text-center shadow-md">
        <h1 className="mb-4 text-2xl font-bold text-gray-900">{t("unlock.title")}</h1>
        <p role={outcome === "ready" || outcome === "working" ? "status" : "alert"} className={`rounded-md px-4 py-3 text-sm ${tone}`}>
          {message}
        </p>
        {(outcome === "ready" || outcome === "working") && (
          <button
            type="button"
            onClick={() => void unlock()}
            disabled={outcome === "working"}
            className="mt-6 min-h-[44px] w-full rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {t("unlock.button")}
          </button>
        )}
        {outcome !== "ready" && outcome !== "working" && (
          <Link to="/login" className="mt-6 inline-flex min-h-[44px] items-center font-medium text-indigo-600 hover:text-indigo-500">
            {t("verifyEmail.goToLogin")}
          </Link>
        )}
      </div>
    </main>
  );
}
