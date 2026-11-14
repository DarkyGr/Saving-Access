import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";

/**
 * "Verify your email" modal shown after logging in with an unverified
 * address (Requirements 2.7, 2.8; task 33.5). The user can resend the
 * verification email or close the modal and keep working until the deadline.
 */

export interface VerifyEmailModalProps {
  /** ISO date (YYYY-MM-DD) after which the account is deactivated, or null. */
  deadline: string | null;
  onClose: () => void;
}

type ResendState = "idle" | "sending" | "sent" | "alreadyVerified" | "tooMany" | "error";

function formatDeadline(iso: string, language: string): string {
  // Parse as a calendar date; "YYYY-MM-DD" alone would be read as UTC midnight.
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString(language, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function VerifyEmailModal({ deadline, onClose }: VerifyEmailModalProps) {
  const { t, i18n } = useTranslation();
  const [state, setState] = useState<ResendState>("idle");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleResend() {
    setState("sending");
    try {
      await apiClient.post("/api/profile/verification-email", { language: i18n.language });
      setState("sent");
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status === 409) setState("alreadyVerified");
      else if (status === 429) setState("tooMany");
      else setState("error");
    }
  }

  const feedback: Partial<Record<ResendState, { key: string; ok: boolean }>> = {
    sent: { key: "verifyEmail.resendSent", ok: true },
    alreadyVerified: { key: "verifyEmail.alreadyVerified", ok: true },
    tooMany: { key: "verifyEmail.resendTooMany", ok: false },
    error: { key: "verifyEmail.resendError", ok: false },
  };
  const message = feedback[state];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vem-title"
      aria-describedby="vem-description"
    >
      <div className="relative mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 id="vem-title" className="mb-2 text-lg font-semibold text-gray-900">
          {t("verifyEmail.modalTitle")}
        </h2>
        <p id="vem-description" className="text-sm text-gray-600">
          {deadline
            ? t("verifyEmail.modalBodyDeadline", {
                date: formatDeadline(deadline, i18n.language),
              })
            : t("verifyEmail.modalBody")}
        </p>

        {message && (
          <p
            role="status"
            className={[
              "mt-4 rounded-md px-3 py-2 text-sm",
              message.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700",
            ].join(" ")}
          >
            {t(message.key)}
          </p>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            ref={closeRef}
            onClick={onClose}
            className="min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {t("verifyEmail.close")}
          </button>
          <button
            type="button"
            onClick={handleResend}
            disabled={state === "sending" || state === "sent" || state === "alreadyVerified"}
            className="min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {state === "sending" ? t("common.loading") : t("verifyEmail.resend")}
          </button>
        </div>
      </div>
    </div>
  );
}
