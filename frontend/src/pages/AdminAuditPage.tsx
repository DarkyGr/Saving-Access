import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { usePaged } from "../hooks/usePaged";
import { FilterSelect, ListToolbar, Pagination, SearchBox } from "../components/list/ListControls";

export const AUDIT_ACTIONS = [
  "account.register",
  "account.login",
  "account.password",
  "account.unlock",
  "account.password_reset",
  "account.export",
  "account.delete",
  "account.2fa_setup",
  "account.recovery_codes",
  "account.trust_device",
  "account.forget_devices",
  "credential.create",
  "credential.edit",
  "credential.delete",
  "credential.reveal",
  "user.role",
  "user.deactivate",
  "user.reactivate",
  "user.unlock",
  "user.reset_2fa",
  "settings.update",
] as const;

interface AuditPerson {
  user_id: number;
  user_code: string;
  username: string;
}

export interface AuditItem {
  log_id: number;
  at: string;
  action: string;
  actor: AuditPerson;
  target: AuditPerson | null;
  record_id: number | null;
  detail: string | null;
}

interface AuditResponse {
  items: AuditItem[];
  truncated: boolean;
}

const dateInput =
  "block rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 " +
  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 min-h-[44px] md:min-h-[40px]";

/**
 * AdminAuditPage — /admin/audit (permission `audit.view`, Requirement 15.4,
 * task 37.4). Who did what and when, newest first, filtered on the server by
 * action, person (username, email or user ID of whoever did it or whoever it
 * was done to) and date. Credentials appear by number only: never their
 * site, login or password.
 */
export default function AdminAuditPage() {
  const { t, i18n } = useTranslation();
  const [action, setAction] = useState("");
  const [query, setQuery] = useState("");
  const [person, setPerson] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Typing waits a moment before asking the server.
  useEffect(() => {
    const timer = window.setTimeout(() => setPerson(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (action) params.action = action;
    if (person) params.q = person;
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    Promise.resolve(apiClient.get<AuditResponse>("/api/admin/audit", { params }))
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled || (axios.isAxiosError(err) && err.response?.status === 401)) return;
        setError(t("errors.generic"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [action, person, from, to, t]);

  const items = useMemo(() => data?.items ?? [], [data]);
  const paged = usePaged(items, 20, `${action}|${person}|${from}|${to}`);
  const when = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "medium" }),
    [i18n.language]
  );

  function who(p: AuditPerson | null) {
    if (!p) return <span className="text-gray-400">—</span>;
    return (
      <>
        <span className="font-medium text-gray-900">{p.username}</span>
        <span className="block font-mono text-xs text-gray-500">{p.user_code}</span>
      </>
    );
  }

  function detail(item: AuditItem) {
    if (item.action === "user.role" && item.detail) {
      const [before, after] = item.detail.split("→");
      return t("audit.roleChange", { from: t(`admin.roles.${before}`), to: t(`admin.roles.${after}`) });
    }
    if (item.record_id !== null) return t("audit.credentialNumber", { id: item.record_id });
    return item.detail ?? "";
  }

  const th = "px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";

  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <h1 className="text-2xl font-bold text-gray-900">{t("audit.title")}</h1>
        <p className="mt-1 mb-6 text-sm text-gray-600">{t("audit.intro")}</p>

        <ListToolbar>
          <SearchBox id="audit-search" value={query} onChange={setQuery} placeholder={t("audit.searchPlaceholder")} />
          <FilterSelect
            id="audit-action"
            label={t("audit.action")}
            value={action}
            onChange={setAction}
            options={AUDIT_ACTIONS.map((a) => ({ value: a, label: t(`audit.actions.${a}`) }))}
          />
          <div className="flex items-center gap-2">
            <label htmlFor="audit-from" className="text-sm text-gray-600 whitespace-nowrap">
              {t("audit.from")}
            </label>
            <input id="audit-from" type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} className={dateInput} />
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="audit-to" className="text-sm text-gray-600 whitespace-nowrap">
              {t("audit.to")}
            </label>
            <input id="audit-to" type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} className={dateInput} />
          </div>
        </ListToolbar>
        <p className="mb-4 text-xs text-gray-500">{t("audit.utcNote")}</p>

        {error && (
          <div role="alert" className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {loading && !data && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("common.loading")}
          </p>
        )}
        {!error && data && items.length === 0 && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("audit.empty")}
          </p>
        )}
        {data?.truncated && (
          <p role="status" className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {t("audit.truncated", { count: items.length })}
          </p>
        )}

        {!error && paged.total > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm" aria-busy={loading}>
            <table className="min-w-full divide-y divide-gray-200 bg-white">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className={th}>{t("audit.when")}</th>
                  <th scope="col" className={th}>{t("audit.who")}</th>
                  <th scope="col" className={th}>{t("audit.action")}</th>
                  <th scope="col" className={th}>{t("audit.target")}</th>
                  <th scope="col" className={th}>{t("audit.detail")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {paged.pageItems.map((item) => (
                  <tr key={item.log_id} className="align-top text-sm">
                    <td className="px-4 py-3 whitespace-nowrap text-gray-600">
                      <time dateTime={item.at}>{when.format(new Date(item.at))}</time>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{who(item.actor)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-900">{t(`audit.actions.${item.action}`)}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{who(item.target)}</td>
                    <td className="px-4 py-3 text-gray-600">{detail(item)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!error && <Pagination paged={paged} id="audit-pages" />}
      </div>
    </main>
  );
}
