import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../../api/apiClient";
import { ReauthCancelled, useReauth } from "../../context/ReauthContext";

type Security = "starttls" | "ssl" | "none";

interface EmailSettings {
  email_verification: boolean;
  smtp: {
    host: string;
    port: number;
    security: Security;
    username: string;
    from_address: string;
    has_password: boolean;
    configured: boolean;
  };
  app_base_url_set: boolean;
  environment_backend: string;
}

const field =
  "mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 min-h-[44px] md:min-h-[40px]";

/**
 * Sign-up email verification and outgoing email (Requirement 16.8, task
 * 37.5). The SMTP password is write-only: the page only knows whether one is
 * saved. "Send a test email" reports the real result of trying.
 */
export default function EmailSettingsCard() {
  const { t } = useTranslation();
  const withReauth = useReauth();
  const [data, setData] = useState<EmailSettings | null>(null);
  const [verification, setVerification] = useState(false);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [security, setSecurity] = useState<Security>("starttls");
  const [username, setUsername] = useState("");
  const [from, setFrom] = useState("");
  const [password, setPassword] = useState("");
  const [clearPassword, setClearPassword] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function adopt(next: EmailSettings) {
    setData(next);
    setVerification(next.email_verification);
    setHost(next.smtp.host);
    setPort(String(next.smtp.port));
    setSecurity(next.smtp.security);
    setUsername(next.smtp.username);
    setFrom(next.smtp.from_address);
    setPassword("");
    setClearPassword(false);
  }

  useEffect(() => {
    Promise.resolve(apiClient.get<EmailSettings>("/api/admin/settings/email"))
      .then((res) => res?.data && adopt(res.data))
      .catch(() => setMessage({ ok: false, text: t("errors.generic") }));
  }, [t]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setMessage(null);
    const portNumber = Number(port);
    if (host.trim() && (!from.trim() || !Number.isInteger(portNumber) || portNumber < 1 || portNumber > 65535)) {
      setMessage({ ok: false, text: t("system.email.incomplete") });
      return;
    }
    setBusy(true);
    try {
      const res = await withReauth(() =>
        apiClient.put<EmailSettings>("/api/admin/settings/email", {
          email_verification: verification,
          smtp: {
            host: host.trim(),
            port: portNumber || 587,
            security,
            username: username.trim(),
            from_address: from.trim(),
            password,
            clear_password: clearPassword,
          },
        })
      );
      adopt(res.data);
      setMessage({ ok: true, text: t("system.saved") });
    } catch (err: unknown) {
      if (err instanceof ReauthCancelled) return;
      const detail = axios.isAxiosError(err) ? (err.response?.data as { detail?: unknown } | undefined)?.detail : undefined;
      setMessage({
        ok: false,
        text: detail === "APP_BASE_URL is not set on the server." ? t("system.email.noBaseUrl") : t("system.email.invalid"),
      });
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setTestResult(null);
    setBusy(true);
    try {
      const res = await apiClient.post<{ ok: boolean; backend: string; error: string | null }>(
        "/api/admin/settings/email/test",
        testTo.trim() ? { to: testTo.trim() } : {}
      );
      setTestResult(
        res.data.ok
          ? { ok: true, text: t(`system.email.testSent.${res.data.backend}`, { defaultValue: t("system.email.testSent.smtp") }) }
          : { ok: false, text: t("system.email.testFailed", { error: res.data.error ?? "" }) }
      );
    } catch {
      setTestResult({ ok: false, text: t("errors.generic") });
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return message ? <p role="alert" className="text-sm text-red-600">{message.text}</p> : null;
  }

  return (
    <section aria-labelledby="email-settings-title" className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 id="email-settings-title" className="text-base font-semibold text-gray-900">
        {t("system.email.title")}
      </h2>
      <form onSubmit={save} noValidate className="mt-3 flex flex-col gap-4">
        <label className="flex items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={verification}
            disabled={!data.app_base_url_set && !verification}
            onChange={(e) => setVerification(e.target.checked)}
            className="mt-0.5 h-4 w-4"
          />
          <span>
            {t("system.email.verification")}
            <span className="block text-xs text-gray-500">
              {data.app_base_url_set ? t("system.email.verificationHelp") : t("system.email.noBaseUrl")}
            </span>
          </span>
        </label>

        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="mb-1 text-sm font-medium text-gray-700">{t("system.email.smtp")}</legend>
          <p className="text-xs text-gray-500 sm:col-span-2">
            {t("system.email.smtpHelp", { backend: data.environment_backend })}
          </p>
          <label className="text-sm text-gray-700">
            {t("system.email.host")}
            <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="smtp.example.com" className={field} />
          </label>
          <label className="text-sm text-gray-700">
            {t("system.email.port")}
            <input value={port} onChange={(e) => setPort(e.target.value)} inputMode="numeric" className={field} />
          </label>
          <label className="text-sm text-gray-700">
            {t("system.email.security")}
            <select value={security} onChange={(e) => setSecurity(e.target.value as Security)} className={field}>
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL/TLS</option>
              <option value="none">{t("system.email.noEncryption")}</option>
            </select>
          </label>
          <label className="text-sm text-gray-700">
            {t("system.email.from")}
            <input value={from} onChange={(e) => setFrom(e.target.value)} type="email" placeholder="vault@example.com" className={field} />
          </label>
          <label className="text-sm text-gray-700">
            {t("system.email.username")}
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" className={field} />
          </label>
          <label className="text-sm text-gray-700">
            {t("system.email.password")}
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="new-password"
              placeholder={data.smtp.has_password ? t("system.email.passwordSaved") : ""}
              className={field}
            />
          </label>
          {data.smtp.has_password && (
            <label className="flex items-center gap-2 text-sm text-gray-700 sm:col-span-2">
              <input type="checkbox" checked={clearPassword} onChange={(e) => setClearPassword(e.target.checked)} className="h-4 w-4" />
              {t("system.email.clearPassword")}
            </label>
          )}
        </fieldset>

        {message && (
          <div role={message.ok ? "status" : "alert"} className={`rounded-md border px-4 py-3 text-sm ${message.ok ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
            {message.text}
          </div>
        )}
        <div>
          <button type="submit" disabled={busy} className="min-h-[44px] rounded-md bg-indigo-600 px-5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60">
            {t("system.email.save")}
          </button>
        </div>
      </form>

      <div className="mt-6 border-t border-gray-100 pt-4">
        <label className="block text-sm text-gray-700">
          {t("system.email.testTo")}
          <input value={testTo} onChange={(e) => setTestTo(e.target.value)} type="email" placeholder={t("system.email.testToHint")} className={field} />
        </label>
        <button
          type="button"
          onClick={() => void sendTest()}
          disabled={busy}
          className="mt-3 min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
        >
          {t("system.email.test")}
        </button>
        {testResult && (
          <p role={testResult.ok ? "status" : "alert"} className={`mt-2 text-sm ${testResult.ok ? "text-green-700" : "text-red-600"}`}>
            {testResult.text}
          </p>
        )}
      </div>
    </section>
  );
}
