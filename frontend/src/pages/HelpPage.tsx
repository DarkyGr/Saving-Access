import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router";
import { useTranslation } from "react-i18next";

import { SearchBox } from "../components/list/ListControls";
import { matchesQuery } from "../lib/text";
import { splitMatches } from "../lib/highlight";
import { USER_GUIDE } from "../help/userGuide";
import { TECHNICAL_GUIDE } from "../help/technicalGuide";
import type { HelpBlock, HelpSection } from "../help/types";
import { usePermissions } from "../hooks/usePermissions";
import { useAuth } from "../context/AuthContext";

const GUIDES = { user: USER_GUIDE, technical: TECHNICAL_GUIDE } as const;
const PATHS = { user: "/help", technical: "/help/technical" } as const;

function blockText(block: HelpBlock): string {
  return Array.isArray(block) ? block.join(" ") : block;
}

function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {splitMatches(text, query).map((piece, i) =>
        piece.match ? (
          <mark key={i} className="rounded bg-amber-100 px-0.5 text-gray-900">
            {piece.text}
          </mark>
        ) : (
          <span key={i}>{piece.text}</span>
        )
      )}
    </>
  );
}

/**
 * HelpPage — /help (user guide) and /help/technical (Admin), Requirement 17,
 * task 37.6. Index, accent-insensitive search with highlighting, and a link
 * per section that can be copied (the page scrolls to it when opened).
 */
export default function HelpPage({ guide }: { guide: "user" | "technical" }) {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const { token, user } = useAuth();
  const permissions = usePermissions(token, user?.role);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const sections: HelpSection[] = GUIDES[guide][i18n.language?.startsWith("es") ? "es" : "en"];

  const visible = useMemo(
    () => sections.filter((s) => matchesQuery(query, [s.title, ...s.blocks.map(blockText)])),
    [sections, query]
  );

  // Opened from a copied link: go to that section.
  useEffect(() => {
    const id = decodeURIComponent(location.hash.replace(/^#/, ""));
    if (id) document.getElementById(id)?.scrollIntoView?.({ block: "start" });
  }, [location.hash]);

  async function copyLink(id: string) {
    const url = `${window.location.origin}${PATHS[guide]}#${id}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(id);
      window.setTimeout(() => setCopied((current) => (current === id ? null : current)), 2000);
    } catch {
      setCopied(null);
    }
  }

  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-2xl font-bold text-gray-900">{t(guide === "user" ? "helpPage.userTitle" : "helpPage.technicalTitle")}</h1>
        <p className="mt-1 text-sm text-gray-600">{t(guide === "user" ? "helpPage.userIntro" : "helpPage.technicalIntro")}</p>
        {guide === "user" && permissions.includes("users.manage") && (
          <p className="mt-1 text-sm">
            <Link to={PATHS.technical} className="font-medium text-indigo-600 hover:text-indigo-500">
              {t("helpPage.toTechnical")}
            </Link>
          </p>
        )}

        <div className="mt-5 mb-6">
          <SearchBox id="help-search" value={query} onChange={setQuery} placeholder={t("helpPage.search")} />
          {query.trim() && (
            <p className="mt-2 text-sm text-gray-600" role="status">
              {t("helpPage.results", { count: visible.length })}
            </p>
          )}
        </div>

        <div className="grid gap-8 md:grid-cols-[14rem_1fr]">
          <nav aria-label={t("helpPage.index")} className="md:sticky md:top-20 md:self-start">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">{t("helpPage.index")}</h2>
            <ol className="space-y-1 text-sm">
              {visible.map((s) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className="block rounded px-2 py-1 text-gray-700 hover:bg-gray-100 hover:text-gray-900">
                    <Marked text={s.title} query={query} />
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <div className="flex min-w-0 flex-col gap-6">
            {visible.length === 0 && <p className="text-sm text-gray-500">{t("helpPage.none")}</p>}
            {visible.map((s) => (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="scroll-mt-20 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <h2 id={`${s.id}-title`} className="text-lg font-semibold text-gray-900">
                    <Marked text={s.title} query={query} />
                  </h2>
                  <button
                    type="button"
                    onClick={() => void copyLink(s.id)}
                    aria-label={t("helpPage.copyLink", { title: s.title })}
                    className="shrink-0 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    {copied === s.id ? t("helpPage.linkCopied") : t("helpPage.link")}
                  </button>
                </div>
                <div className="mt-2 space-y-3 text-sm leading-relaxed text-gray-700">
                  {s.blocks.map((block, i) =>
                    Array.isArray(block) ? (
                      <ul key={i} className="list-disc space-y-1 pl-5">
                        {block.map((item, j) => (
                          <li key={j} className={/^(git |python |powershell |curl)/.test(item) ? "list-none -ml-5 font-mono text-xs" : undefined}>
                            <Marked text={item} query={query} />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p key={i}>
                        <Marked text={block} query={query} />
                      </p>
                    )
                  )}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
