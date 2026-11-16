import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import HelpTip from "../components/form/HelpTip";
import { useFocusFirstError } from "../hooks/useFocusFirstError";
import { ReauthCancelled, useReauth } from "../context/ReauthContext";
import EmailSettingsCard from "../components/admin/EmailSettingsCard";

export interface Parameter {
  key: string;
  group: string;
  value: number;
  default: number;
  minimum: number;
  maximum: number;
}

const GROUPS = ["security", "sessions"] as const;

/**
 * SystemSettingsPage — /admin/settings (permission `settings.manage`,
 * Requirement 16.8, task 37.5). Each security value with its range and
 * suggested value; everything is checked here and again by the server
 * before anything is saved.
 */
export default function SystemSettingsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useState<Parameter[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [tried, setTried] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const withReauth = useReauth();
  const focusFirstError = useFocusFirstError(formRef);

  useEffect(() => {
    Promise.resolve(apiClient.get<Parameter[]>("/api/admin/settings"))
      .then((res) => {
        setParams(res.data);
        setDraft(Object.fromEntries(res.data.map((p) => [p.key, String(p.value)])));
      })
      .catch(() => setMessage({ ok: false, text: t("errors.generic") }))
      .finally(() => setLoading(false));
  }, [t]);

  const errors = useMemo(() => {
    const found: Record<string, string> = {};
    for (const p of params) {
      const raw = draft[p.key] ?? "";
      const value = Number(raw);
      if (!/^\d+$/.test(raw.trim()) || value < p.minimum || value > p.maximum) {
        found[p.key] = t("system.range", { min: p.minimum, max: p.maximum });
      }
    }
    return found;
  }, [params, draft, t]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    setMessage(null);
    if (Object.keys(errors).length > 0) {
      focusFirstError();
      return;
    }
    const changes = Object.fromEntries(
      params.filter((p) => Number(draft[p.key]) !== p.value).map((p) => [p.key, Number(draft[p.key])])
    );
    if (Object.keys(changes).length === 0) {
      setMessage({ ok: true, text: t("system.nothingChanged") });
      return;
    }
    setSaving(true);
    try {
      const res = await withReauth(() => apiClient.put<Parameter[]>("/api/admin/settings", changes));
      setParams(res.data);
      setDraft(Object.fromEntries(res.data.map((p) => [p.key, String(p.value)])));
      setMessage({ ok: true, text: t("system.saved") });
    } catch (err: unknown) {
      if (err instanceof ReauthCancelled) return;
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setMessage({ ok: false, text: status === 422 ? t("system.invalid") : t("errors.generic") });
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900">{t("system.title")}</h1>
        <p className="mt-1 mb-6 text-sm text-gray-600">{t("system.intro")}</p>

        {loading && <p className="text-sm text-gray-500">{t("common.loading")}</p>}

        {!loading && params.length > 0 && (
          <form ref={formRef} onSubmit={save} noValidate className="flex flex-col gap-6">
            {GROUPS.map((group) => (
              <fieldset key={group} className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                <legend className="px-1 text-base font-semibold text-gray-900">{t(`system.groups.${group}`)}</legend>
                <div className="mt-2 flex flex-col gap-5">
                  {params
                    .filter((p) => p.group === group)
                    .map((p) => {
                      const id = `param-${p.key}`;
                      const invalid = tried && Boolean(errors[p.key]);
                      return (
                        <div key={p.key}>
                          <div className="flex items-center gap-1">
                            <label htmlFor={id} className="text-sm font-medium text-gray-700">
                              {t(`system.params.${p.key}.label`)}
                            </label>
                            <HelpTip text={t(`system.params.${p.key}.help`)} topic={t(`system.params.${p.key}.label`)} />
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-3">
                            <input
                              id={id}
                              type="number"
                              inputMode="numeric"
                              min={p.minimum}
                              max={p.maximum}
                              value={draft[p.key] ?? ""}
                              onChange={(e) => setDraft((d) => ({ ...d, [p.key]: e.target.value }))}
                              aria-invalid={invalid}
                              aria-describedby={`${id}-hint${invalid ? ` ${id}-error` : ""}`}
                              className="block w-32 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-[invalid=true]:border-red-500 min-h-[44px] md:min-h-[40px]"
                            />
                            <span id={`${id}-hint`} className="text-xs text-gray-500">
                              {t("system.hint", { min: p.minimum, max: p.maximum, suggested: p.default })}
                            </span>
                            {Number(draft[p.key]) !== p.default && (
                              <button
                                type="button"
                                onClick={() => setDraft((d) => ({ ...d, [p.key]: String(p.default) }))}
                                className="text-xs font-medium text-indigo-600 hover:text-indigo-500"
                              >
                                {t("system.useSuggested")}
                              </button>
                            )}
                          </div>
                          {invalid && (
                            <p id={`${id}-error`} className="mt-1 text-sm text-red-600">
                              {errors[p.key]}
                            </p>
                          )}
                        </div>
                      );
                    })}
                </div>
              </fieldset>
            ))}

            {message && (
              <div
                role={message.ok ? "status" : "alert"}
                className={`rounded-md border px-4 py-3 text-sm ${message.ok ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}
              >
                {message.text}
              </div>
            )}
            <div>
              <button
                type="submit"
                disabled={saving}
                className="min-h-[44px] rounded-md bg-indigo-600 px-5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {saving ? t("common.loading") : t("common.save")}
              </button>
            </div>
          </form>
        )}
        {!loading && (
          <div className="mt-6">
            <EmailSettingsCard />
          </div>
        )}
        {!loading && params.length === 0 && message && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {message.text}
          </div>
        )}
      </div>
    </main>
  );
}
