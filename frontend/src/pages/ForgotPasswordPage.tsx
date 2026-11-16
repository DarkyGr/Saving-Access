import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";

/**
 * ForgotPasswordPage — /forgot-password (Requirement 16.3, task 37.5).
 * Asks for the username or email and always shows the same answer, so the
 * page never reveals whether an account exists.
 */
export default function ForgotPasswordPage() {
  const { t, i18n } = useTranslation();
  const [account, setAccount] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();
  const errorId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!account.trim()) {
      setError(t("form.required"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.post("/api/auth/forgot-password", { account: account.trim(), language: i18n.language });
      setSent(true);
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(status === 429 ? t("forgot.tooMany") : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl bg-white px-8 py-10 shadow-md">
        <h1 className="mb-4 text-center text-2xl font-bold text-gray-900">{t("forgot.title")}</h1>
        {sent ? (
          <p role="status" className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-800">
            {t("forgot.sent")}
          </p>
        ) : (
          <form onSubmit={submit} noValidate className="flex flex-col gap-3">
            <p className="text-sm text-gray-700">{t("forgot.intro")}</p>
            <label htmlFor={fieldId} className="text-sm font-medium text-gray-700">
              {t("forgot.account")}
            </label>
            <input
              id={fieldId}
              value={account}
              onChange={(e) => {
                setAccount(e.target.value);
                setError(null);
              }}
              autoComplete="username"
              aria-invalid={Boolean(error)}
              aria-describedby={error ? errorId : undefined}
              className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-[invalid=true]:border-red-500 min-h-[44px]"
            />
            {error && (
              <p id={errorId} role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={busy}
              className="mt-2 min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {busy ? t("common.loading") : t("forgot.send")}
            </button>
          </form>
        )}
        <p className="mt-6 text-center text-sm">
          <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500">
            {t("verifyEmail.goToLogin")}
          </Link>
        </p>
      </div>
    </main>
  );
}
