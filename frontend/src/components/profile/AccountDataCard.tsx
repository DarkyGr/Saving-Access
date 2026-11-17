import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../../api/apiClient";
import { useAuth } from "../../context/AuthContext";
import { usePreferences } from "../../context/PreferencesContext";
import PasswordInput from "../PasswordInput";

/** Read (and cleared) by the login page to say the account was deleted. */
export const ACCOUNT_DELETED_KEY = "savepass-account-deleted";

const input =
  "mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 min-h-[44px] md:min-h-[40px]";

function errorText(err: unknown, t: (key: string) => string): string {
  const status = axios.isAxiosError(err) ? err.response?.status : undefined;
  if (status === 401) return t("passwordConfirmModal.errorWrongPassword");
  if (status === 400) return t("accountData.wrongCodeOrName");
  if (status === 409) return t("accountData.lastAdmin");
  if (status === 429) return t("settings.tooManyAttempts");
  return t("errors.generic");
}

/**
 * "Your data" in Settings (Requirement 19, task 35.8): download every saved
 * credential, or delete the account. Both ask for the account password and,
 * with two-step verification on, a current code.
 */
export default function AccountDataCard({ card }: { card: (title: string, body: ReactNode) => ReactNode }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { me } = usePreferences();
  const needsCode = Boolean(me?.two_factor?.enabled);

  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [exportPassword, setExportPassword] = useState("");
  const [exportCode, setExportCode] = useState("");
  const [exportMessage, setExportMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const [deletePassword, setDeletePassword] = useState("");
  const [deleteCode, setDeleteCode] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function download(e: FormEvent) {
    e.preventDefault();
    setExportMessage(null);
    if (!exportPassword || (needsCode && !exportCode.trim())) {
      setExportMessage({ ok: false, text: t("form.required") });
      return;
    }
    setBusy(true);
    try {
      const res = await apiClient.post<Blob>(
        "/api/profile/export",
        { account_password: exportPassword, code: exportCode.trim() || null, format },
        { responseType: "blob" }
      );
      // Named here: the browser hides Content-Disposition from cross-origin calls.
      const today = new Date();
      const stamp = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, "0")}${String(today.getDate()).padStart(2, "0")}`;
      const name = `save-pass-export-${stamp}.${format}`;
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setExportPassword("");
      setExportCode("");
      setExportMessage({ ok: true, text: t("accountData.downloaded") });
    } catch (err: unknown) {
      setExportMessage({ ok: false, text: errorText(err, t) });
    } finally {
      setBusy(false);
    }
  }

  async function remove(e: FormEvent) {
    e.preventDefault();
    setDeleteError(null);
    if (!deletePassword || (needsCode && !deleteCode.trim()) || confirmName.trim() !== user?.username) {
      setDeleteError(confirmName.trim() !== user?.username ? t("accountData.typeUsername") : t("form.required"));
      return;
    }
    setBusy(true);
    try {
      await apiClient.post("/api/profile/account/delete", {
        account_password: deletePassword,
        code: deleteCode.trim() || null,
        confirm_username: confirmName.trim(),
      });
      // The server already ended every session of the account; any request
      // still in flight now gets 401 and may reload the login page, so the
      // notice travels in sessionStorage rather than in the route state.
      try {
        window.sessionStorage.setItem(ACCOUNT_DELETED_KEY, "1");
      } catch {
        // No storage: the login page simply shows no notice.
      }
      await logout({ revoked: true });
      navigate("/login", { replace: true });
    } catch (err: unknown) {
      setDeleteError(errorText(err, t));
      setBusy(false);
    }
  }

  const codeField = (id: string, value: string, set: (v: string) => void) =>
    needsCode && (
      <label htmlFor={id} className="block text-sm font-medium text-gray-700">
        {t("twoFactor.codeLabel")} *
        <input
          id={id}
          value={value}
          onChange={(e) => set(e.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={7}
          className={`${input} w-40 font-mono tracking-widest`}
        />
      </label>
    );

  return card(
    t("accountData.title"),
    <div className="space-y-8">
      <form onSubmit={download} noValidate className="max-w-md space-y-4">
        <h3 className="text-base font-semibold text-gray-900">{t("accountData.exportTitle")}</h3>
        <p className="text-sm text-gray-700">{t("accountData.exportIntro")}</p>
        <fieldset className="flex gap-4 text-sm text-gray-700">
          <legend className="sr-only">{t("accountData.format")}</legend>
          {(["csv", "json"] as const).map((value) => (
            <label key={value} className="flex items-center gap-2">
              <input type="radio" name="export-format" checked={format === value} onChange={() => setFormat(value)} className="h-4 w-4" />
              {t(`accountData.${value}`)}
            </label>
          ))}
        </fieldset>
        <PasswordInput
          id="export-password"
          label={`${t("settings.currentPassword")} *`}
          autoComplete="current-password"
          value={exportPassword}
          onChange={(e) => setExportPassword(e.target.value)}
        />
        {codeField("export-code", exportCode, setExportCode)}
        {exportMessage && (
          <p role={exportMessage.ok ? "status" : "alert"} className={`text-sm ${exportMessage.ok ? "text-green-700" : "text-red-600"}`}>
            {exportMessage.text}
          </p>
        )}
        <button type="submit" disabled={busy} className="min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60">
          {t("accountData.download")}
        </button>
      </form>

      <form onSubmit={remove} noValidate className="max-w-md space-y-4 rounded-md border border-red-200 bg-red-50 p-4">
        <h3 className="text-base font-semibold text-red-800">{t("accountData.deleteTitle")}</h3>
        <p className="text-sm text-red-800">{t("accountData.deleteIntro")}</p>
        <PasswordInput
          id="delete-password"
          label={`${t("settings.currentPassword")} *`}
          autoComplete="current-password"
          value={deletePassword}
          onChange={(e) => setDeletePassword(e.target.value)}
        />
        {codeField("delete-code", deleteCode, setDeleteCode)}
        <label htmlFor="delete-confirm" className="block text-sm font-medium text-gray-700">
          {t("accountData.confirmLabel", { username: user?.username ?? "" })}
          <input id="delete-confirm" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} autoComplete="off" className={input} />
        </label>
        {deleteError && (
          <p role="alert" className="text-sm text-red-700">
            {deleteError}
          </p>
        )}
        <button type="submit" disabled={busy} className="min-h-[44px] rounded-md bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60">
          {t("accountData.delete")}
        </button>
      </form>
    </div>
  );
}
