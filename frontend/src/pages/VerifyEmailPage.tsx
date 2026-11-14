import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";

/**
 * VerifyEmailPage — /verify-email?token=… (Requirement 1.10, task 33.5).
 *
 * Opened from the verification email. Posts the token once (link scanners
 * that only GET the page do not consume it) and reports the outcome.
 */

type Outcome = "verifying" | "verified" | "invalid" | "deactivated" | "error";

export default function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [outcome, setOutcome] = useState<Outcome>(token ? "verifying" : "invalid");
  const sentFor = useRef<string | null>(null);

  useEffect(() => {
    // StrictMode runs effects twice in development; a link works only once.
    if (!token || sentFor.current === token) return;
    sentFor.current = token;
    apiClient
      .post("/api/auth/verify-email", { token })
      .then(() => setOutcome("verified"))
      .catch((err: unknown) => {
        const status = axios.isAxiosError(err) ? err.response?.status : undefined;
        if (status === 400 || status === 404 || status === 422) setOutcome("invalid");
        else if (status === 403) setOutcome("deactivated");
        else setOutcome("error");
      });
  }, [token]);

  const ok = outcome === "verified";
  const messageKey = {
    verifying: "verifyEmail.verifying",
    verified: "verifyEmail.verified",
    invalid: "verifyEmail.invalidLink",
    deactivated: "verifyEmail.deactivated",
    error: "verifyEmail.serverError",
  }[outcome];

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl bg-white px-8 py-10 text-center shadow-md">
        <h1 className="mb-4 text-2xl font-bold text-gray-900">{t("verifyEmail.pageTitle")}</h1>
        <p
          role={outcome === "verifying" ? "status" : "alert"}
          className={[
            "rounded-md px-4 py-3 text-sm",
            outcome === "verifying"
              ? "text-gray-600"
              : ok
                ? "bg-green-50 text-green-800"
                : "bg-red-50 text-red-700",
          ].join(" ")}
        >
          {t(messageKey)}
        </p>
        {outcome !== "verifying" && (
          <Link
            to="/login"
            className="mt-6 inline-flex min-h-[44px] items-center font-medium text-indigo-600 hover:text-indigo-500"
          >
            {t("verifyEmail.goToLogin")}
          </Link>
        )}
      </div>
    </main>
  );
}
