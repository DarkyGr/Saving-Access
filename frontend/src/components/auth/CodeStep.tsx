import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

/**
 * Second sign-in step (Requirement 16.1): a 6-digit code from the app, or
 * one of the recovery codes.
 */
export default function CodeStep({
  verify,
  onCancel,
  trustDays = 0,
}: {
  verify: (code: string, rememberDevice: boolean) => Promise<void>;
  onCancel: () => void;
  /** Requirement 21: days "don't ask on this device" lasts; 0 hides it. */
  trustDays?: number;
}) {
  const { t } = useTranslation();
  const [recovery, setRecovery] = useState(false);
  const [remember, setRemember] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldId = useId();
  const errorId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const clean = code.trim();
    const valid = recovery ? clean.replace(/[\s-]/g, "").length === 10 : /^\d{6}$/.test(clean.replace(/\s/g, ""));
    if (!valid) {
      setError(recovery ? t("twoFactor.recoveryFormat") : t("twoFactor.codeFormat"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await verify(recovery ? clean : clean.replace(/\s/g, ""), remember && trustDays > 0);
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const detail = axios.isAxiosError(err) ? (err.response?.data as { detail?: string } | undefined)?.detail : undefined;
      setError(
        status === 401 && detail === "Invalid code."
          ? t("twoFactor.wrongCode")
          : status === 401
            ? t("twoFactor.expired")
            : status === 429
              ? t("login.tooManyAttempts")
              : t("errors.generic")
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3">
      <p className="text-sm text-gray-700">{recovery ? t("twoFactor.recoveryIntro") : t("twoFactor.codeIntro")}</p>
      <label htmlFor={fieldId} className="text-sm font-medium text-gray-700">
        {recovery ? t("twoFactor.recoveryLabel") : t("twoFactor.codeLabel")}
      </label>
      <input
        id={fieldId}
        value={code}
        onChange={(e) => {
          setCode(e.target.value);
          setError(null);
        }}
        inputMode={recovery ? "text" : "numeric"}
        autoComplete={recovery ? "off" : "one-time-code"}
        autoFocus
        maxLength={recovery ? 13 : 7}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-center font-mono text-lg tracking-widest text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-[invalid=true]:border-red-500"
      />
      {error && (
        <p id={errorId} role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {trustDays > 0 && (
        <label className="flex items-start gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="mt-0.5 h-4 w-4" />
          <span>
            {t("trusted.remember", { count: trustDays })}
            <span className="block text-xs text-gray-500">{t("trusted.rememberHelp")}</span>
          </span>
        </label>
      )}
      <button
        type="submit"
        disabled={busy}
        className="min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {busy ? t("common.loading") : t("twoFactor.verify")}
      </button>
      <div className="flex flex-wrap justify-between gap-2 text-sm">
        <button
          type="button"
          onClick={() => {
            setRecovery(!recovery);
            setCode("");
            setError(null);
          }}
          className="min-h-[44px] font-medium text-indigo-600 hover:text-indigo-500"
        >
          {recovery ? t("twoFactor.useApp") : t("twoFactor.useRecovery")}
        </button>
        <button type="button" onClick={onCancel} className="min-h-[44px] font-medium text-gray-600 hover:text-gray-800">
          {t("twoFactor.startOver")}
        </button>
      </div>
    </form>
  );
}
