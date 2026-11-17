import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";
import { START_PATHS, usePreferences, type StartPage } from "../context/PreferencesContext";
import { usePermissions } from "../hooks/usePermissions";
import { useFocusFirstError } from "../hooks/useFocusFirstError";
import { ACCENTS, THEMES, type Accent, type Theme } from "../lib/theme";
import { buildPasswordRules } from "../lib/passwordRules";
import { describeDevice } from "../lib/device";
import { markLanguageChosen } from "../lib/language";
import { PICTURE_MAX_INPUT_BYTES, PICTURE_TYPES, toSquarePicture } from "../lib/image";
import Avatar, { AVATAR_PRESETS, PresetIcon } from "../components/profile/Avatar";
import PasswordInput from "../components/PasswordInput";
import HelpTip from "../components/form/HelpTip";
import ConfirmDialog from "../components/ConfirmDialog";
import TwoFactorSetup, { type SetupStart } from "../components/auth/TwoFactorSetup";
import RecoveryCodes from "../components/auth/RecoveryCodes";
import AccountDataCard from "../components/profile/AccountDataCard";

// Swatch colours (fixed, so each choice shows its own colour in any theme).
const SWATCH: Record<Accent, string> = {
  indigo: "#4f46e5",
  blue: "#2563eb",
  emerald: "#059669",
  violet: "#7c3aed",
  rose: "#e11d48",
  amber: "#d97706",
};
const START_PERMISSION: Record<StartPage, string> = {
  home: "credentials.view",
  credentials: "credentials.view",
  "credentials-new": "credentials.create",
};
const DISPLAY_NAME = /^[\p{L}\p{N} .,'_-]{2,60}$/u;

const input =
  "block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 " +
  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 min-h-[44px] md:min-h-[40px]";
const primary =
  "inline-flex min-h-[44px] items-center justify-center rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60";
const secondary =
  "inline-flex min-h-[44px] items-center justify-center rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60";

function Card({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
      <h2 id={id} className="mb-4 text-lg font-semibold text-gray-900">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Status({ kind, text }: { kind: "ok" | "error"; text: string }) {
  return (
    <p role={kind === "error" ? "alert" : "status"} className={`mt-2 text-sm ${kind === "error" ? "text-red-600" : "text-green-700"}`}>
      {text}
    </p>
  );
}

// ── Profile ────────────────────────────────────────────────────────────────

function ProfileCard() {
  const { t } = useTranslation();
  const { me, prefs, avatarUrl, setDisplayName, setAvatarPreset, uploadAvatar, clearAvatar } = usePreferences();
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => setName(me?.display_name ?? ""), [me?.display_name]);

  if (!me) return <p className="text-sm text-gray-500">{t("common.loading")}</p>;

  async function saveName(e: FormEvent) {
    e.preventDefault();
    const value = name.trim();
    if (value && !DISPLAY_NAME.test(value)) {
      setNameError(t("settings.displayNameInvalid"));
      return;
    }
    setNameError(null);
    try {
      await setDisplayName(value);
      setStatus({ kind: "ok", text: t("settings.saved") });
    } catch {
      setStatus({ kind: "error", text: t("errors.generic") });
    }
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setStatus(null);
    try {
      await action();
      setStatus({ kind: "ok", text: t("settings.saved") });
    } catch {
      setStatus({ kind: "error", text: t("settings.pictureFailed") });
    } finally {
      setBusy(false);
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    if (!PICTURE_TYPES.includes(file.type) || file.size > PICTURE_MAX_INPUT_BYTES) {
      setStatus({ kind: "error", text: t("settings.pictureRules") });
      return;
    }
    await run(async () => uploadAvatar(await toSquarePicture(file)));
    if (fileRef.current) fileRef.current.value = "";
  }

  const shown = me.display_name || me.username;
  return (
    <Card id="settings-profile" title={t("settings.profile")}>
      <div className="flex flex-col gap-6 sm:flex-row">
        <div className="flex flex-col items-center gap-2 sm:w-40">
          <Avatar name={shown} preset={prefs.avatar_preset} imageUrl={avatarUrl} size="lg" />
          <p className="text-center text-sm font-medium text-gray-900">{shown}</p>
        </div>
        <div className="min-w-0 flex-1 space-y-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-gray-500">
                {t("settings.userCode")}
                <HelpTip text={t("help.userCode")} topic={t("settings.userCode")} />
              </dt>
              <dd className="font-mono text-gray-900" data-testid="user-code">{me.user_code}</dd>
            </div>
            <div>
              <dt className="text-gray-500">{t("settings.username")}</dt>
              <dd className="text-gray-900">{me.username}</dd>
            </div>
            <div>
              <dt className="text-gray-500">{t("settings.email")}</dt>
              <dd className="break-all text-gray-900">{me.email}</dd>
            </div>
            <div>
              <dt className="text-gray-500">{t("admin.tableHeaderRole")}</dt>
              <dd className="text-gray-900">{t(`admin.roles.${me.role}`)}</dd>
            </div>
          </dl>

          <form onSubmit={saveName} noValidate className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label htmlFor="settings-display-name" className="inline-block mb-1 text-sm font-medium text-gray-700">
                {t("settings.displayName")}
              </label>
              <HelpTip text={t("help.displayName")} topic={t("settings.displayName")} />
              <input
                id="settings-display-name"
                value={name}
                maxLength={60}
                onChange={(e) => {
                  setName(e.target.value);
                  setNameError(null);
                }}
                placeholder={me.username}
                aria-invalid={nameError ? true : undefined}
                aria-describedby={nameError ? "settings-display-name-error" : undefined}
                className={`${input} ${nameError ? "border-red-500" : ""}`}
              />
              {nameError && (
                <p id="settings-display-name-error" role="alert" className="mt-1 text-sm text-red-600">
                  {nameError}
                </p>
              )}
            </div>
            <button type="submit" className={primary}>
              {t("settings.save")}
            </button>
          </form>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-gray-700">{t("settings.avatar")}</legend>
            <div className="grid grid-cols-6 gap-2 sm:grid-cols-12">
              {AVATAR_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  disabled={busy}
                  onClick={() => run(() => setAvatarPreset(preset))}
                  aria-pressed={prefs.avatar_preset === preset && !prefs.has_avatar_image}
                  aria-label={t(`settings.presets.${preset}`)}
                  title={t(`settings.presets.${preset}`)}
                  className={[
                    "h-11 w-11 rounded-full p-0.5",
                    prefs.avatar_preset === preset && !prefs.has_avatar_image ? "ring-2 ring-indigo-600 ring-offset-2" : "",
                  ].join(" ")}
                >
                  <PresetIcon preset={preset} />
                </button>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <input
                ref={fileRef}
                id="settings-picture"
                type="file"
                accept={PICTURE_TYPES.join(",")}
                className="sr-only"
                onChange={(e) => onFile(e.target.files?.[0])}
              />
              <label htmlFor="settings-picture" className={`${secondary} cursor-pointer`}>
                {t("settings.uploadPicture")}
              </label>
              {(prefs.has_avatar_image || prefs.avatar_preset) && (
                <button type="button" disabled={busy} onClick={() => run(clearAvatar)} className={secondary}>
                  {t("settings.useInitials")}
                </button>
              )}
            </div>
            <p className="mt-1 text-xs text-gray-500">{t("settings.pictureRules")}</p>
          </fieldset>
          {status && <Status {...status} />}
        </div>
      </div>
    </Card>
  );
}

// ── Preferences ────────────────────────────────────────────────────────────

function PreferencesCard() {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const permissions = usePermissions(token, user?.role);
  const { prefs, updatePreferences } = usePreferences();
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function save(changes: Parameters<typeof updatePreferences>[0]) {
    setStatus(null);
    try {
      await updatePreferences(changes);
      setStatus({ kind: "ok", text: t("settings.saved") });
    } catch {
      setStatus({ kind: "error", text: t("errors.generic") });
    }
  }

  const startPages = (Object.keys(START_PATHS) as StartPage[]).filter((p) => permissions.includes(START_PERMISSION[p]));
  const language = (prefs.language ?? (i18n.language?.startsWith("es") ? "es" : "en")) as "en" | "es";

  return (
    <Card id="settings-preferences" title={t("settings.preferences")}>
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="settings-language" className="mb-1 block text-sm font-medium text-gray-700">
            {t("settings.language")}
          </label>
          <select
            id="settings-language"
            value={language}
            onChange={(e) => {
              void i18n.changeLanguage(e.target.value);
              markLanguageChosen(e.target.value as "en" | "es");
              void save({ language: e.target.value as "en" | "es" });
            }}
            className={input}
          >
            <option value="en">English</option>
            <option value="es">Español</option>
          </select>
        </div>
        <div>
          <label htmlFor="settings-start" className="inline-block mb-1 text-sm font-medium text-gray-700">
            {t("settings.startPage")}
          </label>
          <HelpTip text={t("help.startPage")} topic={t("settings.startPage")} />
          <select
            id="settings-start"
            value={startPages.includes(prefs.start_page) ? prefs.start_page : "home"}
            onChange={(e) => save({ start_page: e.target.value as StartPage })}
            className={input}
          >
            {startPages.map((p) => (
              <option key={p} value={p}>
                {t(`settings.startPages.${p}`)}
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className="mb-1 text-sm font-medium text-gray-700">{t("settings.theme")}</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("settings.theme")}>
            {THEMES.map((theme: Theme) => (
              <button
                key={theme}
                type="button"
                role="radio"
                aria-checked={prefs.theme === theme}
                onClick={() => save({ theme })}
                className={[
                  "min-h-[44px] rounded-md border px-3 text-sm",
                  prefs.theme === theme ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-gray-300 text-gray-700 hover:bg-gray-50",
                ].join(" ")}
              >
                {t(`settings.themes.${theme}`)}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-1 text-sm font-medium text-gray-700">{t("settings.accent")}</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("settings.accent")}>
            {ACCENTS.map((accent) => (
              <button
                key={accent}
                type="button"
                role="radio"
                aria-checked={prefs.accent === accent}
                aria-label={t(`settings.accents.${accent}`)}
                title={t(`settings.accents.${accent}`)}
                onClick={() => save({ accent })}
                className={[
                  "h-11 w-11 rounded-full border-2",
                  prefs.accent === accent ? "border-gray-900" : "border-transparent",
                ].join(" ")}
                style={{ backgroundColor: SWATCH[accent] }}
              />
            ))}
          </div>
        </fieldset>

        <div className="sm:col-span-2">
          <label className="inline-flex min-h-[44px] cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={prefs.private_mode}
              onChange={(e) => save({ private_mode: e.target.checked })}
              className="h-5 w-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-gray-700">{t("settings.privateMode")}</span>
          </label>
          <HelpTip text={t("help.privateMode")} topic={t("settings.privateMode")} />
        </div>
      </div>
      {status && <Status {...status} />}
    </Card>
  );
}

// ── Password ───────────────────────────────────────────────────────────────

interface PasswordErrors {
  current?: string;
  next?: string[];
  confirm?: string;
}

function PasswordCard() {
  const { t } = useTranslation();
  const rules = buildPasswordRules(t);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const focusFirstError = useFocusFirstError(formRef);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    const found: PasswordErrors = {};
    if (!current) found.current = t("form.required");
    const unmet = rules.filter((r) => !r.test(next)).map((r) => r.label);
    if (unmet.length) found.next = unmet;
    if (next !== confirm) found.confirm = t("passwordRules.mismatch");
    setErrors(found);
    if (Object.keys(found).length) {
      focusFirstError();
      return;
    }
    setBusy(true);
    try {
      await apiClient.post("/api/profile/password", {
        current_password: current,
        new_password: next,
        new_password_confirmation: confirm,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setStatus({ kind: "ok", text: t("settings.passwordChanged") });
    } catch (err: unknown) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setErrors({ current: t("passwordConfirmModal.errorWrongPassword") });
        focusFirstError();
      } else if (detail === "The new password must be different.") {
        setErrors({ next: [t("settings.passwordSame")] });
        focusFirstError();
      } else if (axios.isAxiosError(err) && err.response?.status === 429) {
        setStatus({ kind: "error", text: t("settings.tooManyAttempts") });
      } else {
        setStatus({ kind: "error", text: t("errors.generic") });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card id="settings-password" title={t("settings.password")}>
      <form ref={formRef} onSubmit={submit} noValidate className="max-w-md space-y-4">
        <PasswordInput
          id="settings-current-password"
          label={`${t("settings.currentPassword")} *`}
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={errors.current}
        />
        <div>
          <PasswordInput
            id="settings-new-password"
            label={`${t("settings.newPassword")} *`}
            help={t("help.newPassword")}
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            aria-invalid={errors.next ? true : undefined}
            aria-describedby="settings-new-password-rules"
          />
          <ul id="settings-new-password-rules" className="mt-2 space-y-1 text-sm" aria-label={t("passwordRules.title")}>
            {rules.map((r) => {
              const ok = r.test(next);
              return (
                <li key={r.key} className={ok ? "text-green-700" : errors.next ? "text-red-600" : "text-gray-500"}>
                  {ok ? "✓" : "•"} {r.label}
                </li>
              );
            })}
          </ul>
          {errors.next?.includes(t("settings.passwordSame")) && (
            <p role="alert" className="mt-1 text-sm text-red-600">
              {t("settings.passwordSame")}
            </p>
          )}
        </div>
        <PasswordInput
          id="settings-confirm-password"
          label={`${t("settings.confirmPassword")} *`}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
        />
        <button type="submit" disabled={busy} className={primary}>
          {t("settings.changePassword")}
        </button>
        {status && <Status {...status} />}
      </form>
    </Card>
  );
}

// ── Two-step verification (task 37.5) ─────────────────────────────────────

type TwoFactorMode = "idle" | "password" | "setup" | "renew" | "codes";

function TwoFactorCard() {
  const { t, i18n } = useTranslation();
  const { me, reloadMe } = usePreferences();
  const status = me?.two_factor;
  const [mode, setMode] = useState<TwoFactorMode>("idle");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [setup, setSetup] = useState<SetupStart | null>(null);
  const [codes, setCodes] = useState<string[]>([]);

  function reset(next: TwoFactorMode = "idle") {
    setMode(next);
    setPassword("");
    setCode("");
    setError(null);
  }

  function failure(err: unknown) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined;
    setError(
      status === 401
        ? t("passwordConfirmModal.errorWrongPassword")
        : status === 400
          ? t("twoFactor.wrongCode")
          : status === 429
            ? t("settings.tooManyAttempts")
            : t("errors.generic")
    );
  }

  async function startSetup(e: FormEvent) {
    e.preventDefault();
    if (!password) {
      setError(t("form.required"));
      return;
    }
    setBusy(true);
    try {
      const res = await apiClient.post<SetupStart>("/api/profile/2fa/setup", { account_password: password });
      setSetup(res.data);
      reset("setup");
    } catch (err: unknown) {
      failure(err);
    } finally {
      setBusy(false);
    }
  }

  async function renew(e: FormEvent) {
    e.preventDefault();
    if (!password || !/^\d{6}$/.test(code.replace(/\s/g, ""))) {
      setError(!password ? t("form.required") : t("twoFactor.codeFormat"));
      return;
    }
    setBusy(true);
    try {
      const res = await apiClient.post<{ recovery_codes: string[] }>("/api/profile/2fa/recovery-codes", {
        account_password: password,
        code: code.replace(/\s/g, ""),
      });
      setCodes(res.data.recovery_codes);
      reset("codes");
    } catch (err: unknown) {
      failure(err);
    } finally {
      setBusy(false);
    }
  }

  const since = status?.enabled_at
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" }).format(new Date(status.enabled_at))
    : null;
  const low = Boolean(status?.enabled && status.recovery_codes_left <= 3);

  return (
    <Card id="settings-two-factor" title={t("twoFactor.cardTitle")}>
      {mode === "idle" && (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">
            {status?.enabled ? t("twoFactor.enabledSince", { date: since }) : t("twoFactor.notEnabled")}
          </p>
          {status?.enabled && (
            <p className={`text-sm ${low ? "font-medium text-amber-700" : "text-gray-600"}`}>
              {t("twoFactor.codesLeft", { count: status.recovery_codes_left })}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={secondary} onClick={() => reset("password")}>
              {status?.enabled ? t("twoFactor.newDevice") : t("twoFactor.setUp")}
            </button>
            {status?.enabled && (
              <button type="button" className={secondary} onClick={() => reset("renew")}>
                {t("twoFactor.newCodes")}
              </button>
            )}
          </div>
        </div>
      )}

      {(mode === "password" || mode === "renew") && (
        <form onSubmit={mode === "password" ? startSetup : renew} noValidate className="max-w-md space-y-4">
          <p className="text-sm text-gray-700">{mode === "password" ? t("twoFactor.newDeviceIntro") : t("twoFactor.newCodesIntro")}</p>
          <PasswordInput
            id="two-factor-password"
            label={`${t("settings.currentPassword")} *`}
            autoComplete="current-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError(null);
            }}
          />
          {mode === "renew" && (
            <div>
              <label htmlFor="two-factor-code" className="block text-sm font-medium text-gray-700">
                {t("twoFactor.codeLabel")} *
              </label>
              <input
                id="two-factor-code"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value);
                  setError(null);
                }}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                className={`${input} mt-1 w-40 font-mono tracking-widest`}
              />
            </div>
          )}
          {error && <Status kind="error" text={error} />}
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className={primary}>
              {t("twoFactor.continue")}
            </button>
            <button type="button" className={secondary} onClick={() => reset()}>
              {t("common.cancel")}
            </button>
          </div>
        </form>
      )}

      {mode === "setup" && setup && (
        <div className="max-w-md space-y-4">
          <TwoFactorSetup
            start={async () => setup}
            confirm={async (value) => {
              const res = await apiClient.post<{ recovery_codes: string[] }>("/api/profile/2fa/confirm", { code: value });
              setCodes(res.data.recovery_codes);
              setSetup(null);
              reset("codes");
            }}
          />
          <button type="button" className={secondary} onClick={() => reset()}>
            {t("common.cancel")}
          </button>
        </div>
      )}

      {mode === "codes" && (
        <div className="max-w-md">
          <RecoveryCodes
            codes={codes}
            doneLabel={t("twoFactor.done")}
            onDone={() => {
              setCodes([]);
              reset();
              void reloadMe();
            }}
          />
        </div>
      )}
    </Card>
  );
}

// ── Sessions ───────────────────────────────────────────────────────────────

interface SessionItem {
  session_id: string;
  user_agent: string | null;
  client_ip: string | null;
  started: string;
  last_active: string;
  current: boolean;
}

function SessionsCard() {
  const { t, i18n } = useTranslation();
  const [sessions, setSessions] = useState<SessionItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [ending, setEnding] = useState<SessionItem | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiClient.get<SessionItem[]>("/api/profile/sessions");
      setSessions(res.data);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  async function endSession() {
    if (!ending) return;
    setBusy(true);
    try {
      await apiClient.delete(`/api/profile/sessions/${ending.session_id}`);
    } catch {
      // Already gone: the reload below shows the truth.
    } finally {
      setBusy(false);
      setEnding(null);
      await load();
    }
  }

  return (
    <Card id="settings-sessions" title={t("settings.sessions")}>
      {failed && <Status kind="error" text={t("errors.generic")} />}
      {sessions === null && !failed && <p className="text-sm text-gray-500">{t("common.loading")}</p>}
      {sessions && (
        <ul className="divide-y divide-gray-100">
          {sessions.map((s) => {
            const { browser, os } = describeDevice(s.user_agent);
            const name = [browser, os].filter(Boolean).join(" · ") || t("settings.unknownDevice");
            return (
              <li key={s.session_id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    {name}
                    {s.current && (
                      <span className="ml-2 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                        {t("settings.thisDevice")}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-500">
                    {t("settings.lastActive", { when: when.format(new Date(s.last_active)) })}
                    {s.client_ip ? ` · ${s.client_ip}` : ""}
                  </p>
                </div>
                {s.current ? (
                  <span className="text-xs text-gray-500">{t("settings.endWithLogout")}</span>
                ) : (
                  <button type="button" onClick={() => setEnding(s)} className={secondary}>
                    {t("settings.endSession")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {ending && (
        <ConfirmDialog
          title={t("settings.endSessionTitle")}
          message={t("settings.endSessionMessage")}
          confirmLabel={t("settings.endSession")}
          cancelLabel={t("common.cancel")}
          onConfirm={endSession}
          onCancel={() => setEnding(null)}
          busy={busy}
        />
      )}
    </Card>
  );
}

/**
 * SettingsPage — /settings (task 37.3, Requirement 14): profile, preferences,
 * password and active sessions. Opened from the account menu.
 */
export default function SettingsPage() {
  const { t } = useTranslation();
  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">{t("settings.title")}</h1>
        <ProfileCard />
        <PreferencesCard />
        <PasswordCard />
        <TwoFactorCard />
        <SessionsCard />
        <AccountDataCard card={(title, body) => <Card id="settings-data" title={title}>{body}</Card>} />
      </div>
    </main>
  );
}
