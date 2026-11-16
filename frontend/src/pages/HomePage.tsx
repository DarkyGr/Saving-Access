import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";

import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";
import type { Credential } from "./ViewSearchPage";
import { KeyIcon, PlusIcon } from "../components/icons";

const RECENT = 5;

/**
 * HomePage — / (Requirement 13.3, task 37.2).
 *
 * How many credentials the user has (and how many sign in with an email or
 * a username) and the most recently changed ones, with links to the vault.
 * Nothing secret is shown: the list endpoint never returns passwords.
 */
export default function HomePage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const [credentials, setCredentials] = useState<Credential[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<Credential[]>("/api/credentials")
      .then((res) => !cancelled && setCredentials(res.data))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const total = credentials?.length ?? 0;
  const byUsername = credentials?.filter((c) => c.is_username_login).length ?? 0;
  const recent = [...(credentials ?? [])]
    .sort((a, b) => (b.last_changed ?? "").localeCompare(a.last_changed ?? ""))
    .slice(0, RECENT);
  const dateFormat = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  const stat = (label: string, value: number) => (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums text-gray-900">{value}</p>
    </div>
  );

  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          {t("home.title", { username: user?.username ?? "" })}
        </h1>

        {failed && (
          <div role="alert" className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {t("errors.generic")}
          </div>
        )}
        {credentials === null && !failed && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("common.loading")}
          </p>
        )}

        {credentials !== null && (
          <>
            <div className="mb-8 grid gap-4 sm:grid-cols-3">
              {stat(t("home.total"), total)}
              {stat(t("home.withEmail"), total - byUsername)}
              {stat(t("home.withUsername"), byUsername)}
            </div>

            <section aria-labelledby="home-recent">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 id="home-recent" className="text-lg font-semibold text-gray-900">
                  {t("home.recent")}
                </h2>
                {total > 0 && (
                  <Link to="/credentials" className="inline-flex min-h-[44px] items-center gap-1 text-sm font-medium text-indigo-700 hover:underline">
                    <KeyIcon className="h-4 w-4" />
                    {t("home.seeAll")}
                  </Link>
                )}
              </div>

              {total === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center">
                  <p className="mb-4 text-sm text-gray-600">{t("home.empty")}</p>
                  <Link
                    to="/credentials/new"
                    className="inline-flex min-h-[44px] items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                  >
                    <PlusIcon className="h-4 w-4" />
                    {t("credentials.addNew")}
                  </Link>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                  {recent.map((c) => (
                    <li key={c.credential_id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-gray-900">{c.website_name}</p>
                        <p className="truncate text-sm text-gray-500">{c.email_or_username}</p>
                      </div>
                      {c.last_changed && (
                        <time dateTime={c.last_changed} className="shrink-0 text-xs text-gray-500">
                          {dateFormat.format(new Date(c.last_changed))}
                        </time>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}
