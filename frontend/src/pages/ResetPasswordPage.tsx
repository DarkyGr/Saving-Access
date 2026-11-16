import { useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import PasswordInput from "../components/PasswordInput";
import { buildPasswordRules } from "../lib/passwordRules";
import { useFocusFirstError } from "../hooks/useFocusFirstError";

type Outcome = "form" | "done" | "invalid";

/**
 * ResetPasswordPage — /reset-password?token=… (Requirement 16.3, task 37.5).
 * The new password follows the sign-up rules. Afterwards every session is
 * closed and signing in still asks for the two-step code.
 */
export default function ResetPasswordPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const rules = buildPasswordRules(t);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [tried, setTried] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(token ? "form" : "invalid");
  const formRef = useRef<HTMLFormElement>(null);
  const focusFirstError = useFocusFirstError(formRef);

  const unmet = rules.filter((r) => !r.test(password));
  const mismatch = confirm !== password;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    setError(null);
    if (unmet.length || mismatch || !confirm) {
      focusFirstError();
      return;
    }
    setBusy(true);
    try {
      await apiClient.post("/api/auth/reset-password", { token, password, password_confirmation: confirm });
      setOutcome("done");
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const detail = axios.isAxiosError(err) ? (err.response?.data as { detail?: unknown } | undefined)?.detail : undefined;
      if (status === 400 && detail === "Invalid or expired link.") setOutcome("invalid");
      else setError(status === 429 ? t("forgot.tooMany") : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl bg-white px-8 py-10 shadow-md">
        <h1 className="mb-4 text-center text-2xl font-bold text-gray-900">{t("reset.title")}</h1>
        {outcome === "done" && (
          <p role="status" className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-800">
            {t("reset.done")}
          </p>
        )}
        {outcome === "invalid" && (
          <p role="alert" className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {t("reset.invalid")}{" "}
            <Link to="/forgot-password" className="font-medium underline">
              {t("reset.askAgain")}
            </Link>
          </p>
        )}
        {outcome === "form" && (
          <form ref={formRef} onSubmit={submit} noValidate className="flex flex-col gap-4">
            <div>
              <PasswordInput
                id="reset-password"
                label={`${t("settings.newPassword")} *`}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={tried && unmet.length > 0 ? true : undefined}
                aria-describedby="reset-password-rules"
              />
              <ul id="reset-password-rules" className="mt-2 space-y-1 text-sm" aria-label={t("passwordRules.title")}>
                {rules.map((r) => {
                  const ok = r.test(password);
                  return (
                    <li key={r.key} className={ok ? "text-green-700" : tried ? "text-red-600" : "text-gray-500"}>
                      {ok ? "✓" : "•"} {r.label}
                    </li>
                  );
                })}
              </ul>
            </div>
            <PasswordInput
              id="reset-confirm"
              label={`${t("settings.confirmPassword")} *`}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              error={tried && (mismatch || !confirm) ? t("passwordRules.mismatch") : undefined}
            />
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
            <p className="text-xs text-gray-500">{t("reset.note")}</p>
            <button
              type="submit"
              disabled={busy}
              className="min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {busy ? t("common.loading") : t("reset.submit")}
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
