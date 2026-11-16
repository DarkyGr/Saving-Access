import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import QrCode from "./QrCode";

export interface SetupStart {
  secret: string;
  otpauth_uri: string;
}

/**
 * Scan (or type) the secret into an authenticator app and confirm it with a
 * code (Requirement 16.1, task 37.5). Used at the first sign-in and from
 * Settings; the caller says how to start and how to confirm.
 */
export default function TwoFactorSetup({
  start,
  confirm,
}: {
  start: () => Promise<SetupStart>;
  confirm: (code: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [setup, setSetup] = useState<SetupStart | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);
  const fieldId = useId();
  const errorId = useId();

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start()
      .then(setSetup)
      .catch((err: unknown) => {
        const status = axios.isAxiosError(err) ? err.response?.status : undefined;
        setError(status === 401 ? t("twoFactor.expired") : t("errors.generic"));
      });
  }, [start, t]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{6}$/.test(code.replace(/\s/g, ""))) {
      setError(t("twoFactor.codeFormat"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirm(code.replace(/\s/g, ""));
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(status === 400 ? t("twoFactor.wrongCode") : status === 401 ? t("twoFactor.expired") : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-700">
        <li>{t("twoFactor.step1")}</li>
        <li>{t("twoFactor.step2")}</li>
        <li>{t("twoFactor.step3")}</li>
      </ol>
      {setup && (
        <div className="flex flex-col items-center gap-3">
          <a href={setup.otpauth_uri} className="rounded-md border border-gray-200 p-2" aria-label={t("twoFactor.openInApp")}>
            <QrCode value={setup.otpauth_uri} label={t("twoFactor.qrLabel")} />
          </a>
          <p className="text-center text-xs text-gray-500">{t("twoFactor.manual")}</p>
          <code className="break-all rounded bg-gray-100 px-2 py-1 text-center font-mono text-sm text-gray-900" data-testid="totp-secret">
            {setup.secret.replace(/(.{4})/g, "$1 ").trim()}
          </code>
        </div>
      )}
      <form onSubmit={submit} noValidate className="flex flex-col gap-2">
        <label htmlFor={fieldId} className="text-sm font-medium text-gray-700">
          {t("twoFactor.codeLabel")}
        </label>
        <input
          id={fieldId}
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            setError(null);
          }}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={7}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          className="block w-40 rounded-md border border-gray-300 bg-white px-3 py-2 text-center font-mono text-lg tracking-widest text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-[invalid=true]:border-red-500"
        />
        {error && (
          <p id={errorId} role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !setup}
          className="mt-2 min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {busy ? t("common.loading") : t("twoFactor.confirm")}
        </button>
      </form>
    </div>
  );
}
