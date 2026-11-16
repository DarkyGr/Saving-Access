import { useState, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useVisibilityTimer } from "../hooks/useVisibilityTimer";
import { usePaged } from "../hooks/usePaged";
import { useListView } from "../hooks/useListView";
import { matchesQuery } from "../lib/text";
import { clearLaterIfCopied, copySecret } from "../lib/clipboard";
import { usePrivacy } from "../context/PreferencesContext";
import PasswordConfirmModal from "../components/PasswordConfirmModal";
import AlreadyVisibleModal from "../components/AlreadyVisibleModal";
import ConfirmDeleteModal from "../components/ConfirmDeleteModal";
import { FilterSelect, ListToolbar, Pagination, SearchBox, ViewToggle } from "../components/list/ListControls";
import { PlusIcon } from "../components/icons";

// ── Types ────────────────────────────────────────────────────────────────────

export interface Credential {
  credential_id: number;
  website_name: string;
  email_or_username: string;
  is_username_login: boolean;
  /** Always null from list endpoint; filled in by the reveal flow */
  password: string | null;
  /** Last creation or edit, UTC ISO 8601 (task 37.2) */
  last_changed?: string;
}

type LoginType = "" | "email" | "username";

// ── Modal states ─────────────────────────────────────────────────────────────

type ModalState =
  | { type: "none" }
  | { type: "alreadyVisible"; pendingId: number }
  | { type: "revealConfirm"; targetId: number }
  | { type: "deleteConfirm"; targetId: number; websiteName: string }
  | { type: "deletePasswordConfirm"; targetId: number; websiteName: string };

interface RevealedRow {
  credentialId: number;
  plaintext: string;
}

// ── Icons ────────────────────────────────────────────────────────────────────

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const EyeOpenIcon = () => (
  <Svg>
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);
const EyeClosedIcon = () => (
  <Svg>
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </Svg>
);
const EditIcon = () => (
  <Svg>
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </Svg>
);
const TrashIcon = () => (
  <Svg>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Svg>
);

const iconButton = [
  "inline-flex items-center justify-center rounded",
  "p-2 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:p-1.5",
  "text-gray-500 focus:outline-none focus:ring-2 focus:ring-offset-1",
  "transition-colors duration-100",
].join(" ");

// ── Component ────────────────────────────────────────────────────────────────

/**
 * ViewSearchPage — /credentials
 *
 * Requirements 5.1–5.14, 7.1–7.7 and 13.4 (task 37.2):
 *  5.2  The search box filters by website_name or email/username: partial,
 *       case- and accent-insensitive. The page loads the user's own list
 *       once (5.3: the backend returns only theirs) and filters it locally,
 *       so results follow every keystroke.
 *  13.4 Filter by login type, pagination "X–Y of Z" (10/20/30/50/100), list
 *       or grid saved in the account, distinct "no data" / "no results".
 *  5.4–5.13 Masked passwords, account-password prompt on every reveal,
 *       one visible password at a time with a 60-second timer.
 *  7.1–7.7 Delete with confirmation and the account password.
 */
export default function ViewSearchPage() {
  const { t } = useTranslation();
  const { mask } = usePrivacy();

  // ── List state ──────────────────────────────────────────────────────────

  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loginType, setLoginType] = useState<LoginType>("");
  const [view, setView] = useListView("credentials", "list");

  const filtered = useMemo(
    () =>
      credentials.filter(
        (c) =>
          matchesQuery(searchQuery, [c.website_name, c.email_or_username]) &&
          (loginType === "" || (loginType === "username") === c.is_username_login)
      ),
    [credentials, searchQuery, loginType]
  );
  const paged = usePaged(filtered, view === "grid" ? 30 : 10, `${searchQuery}|${loginType}|${view}`);

  // ── Reveal state (one row at a time, Req 5.10) ──────────────────────────

  const [revealedRow, setRevealedRow] = useState<RevealedRow | null>(null);
  // Task 37.5: "Copied" next to the password that was copied (cleared in 30 s).
  const [copied, setCopied] = useState<number | null>(null);
  const timer = useVisibilityTimer(60_000);

  useEffect(() => {
    if (!timer.isVisible && revealedRow !== null) {
      setRevealedRow(null);
    }
    // We intentionally only react to isVisible transitions
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timer.isVisible]);

  // ── Modal state ─────────────────────────────────────────────────────────

  const [modal, setModal] = useState<ModalState>({ type: "none" });
  const [modalError, setModalError] = useState<string | undefined>(undefined);
  const [isModalLoading, setIsModalLoading] = useState(false);
  const [isDeletingId, setIsDeletingId] = useState<number | null>(null);

  const loadCredentials = useCallback(async () => {
    setFetchError(null);
    try {
      const response = await apiClient.get<Credential[]>("/api/credentials");
      setCredentials(response.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        // The response interceptor in apiClient handles the redirect.
        return;
      }
      setFetchError(t("errors.generic"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadCredentials();
  }, [loadCredentials]);

  // ── Helpers ─────────────────────────────────────────────────────────────

  function maskCurrentRow() {
    timer.stopTimer();
    setRevealedRow(null);
  }

  function modalErrorFor(err: unknown): string {
    if (axios.isAxiosError(err)) {
      const status = err.response?.status;
      if (status === 401) return t("passwordConfirmModal.errorWrongPassword");
      if (status === 403) return t("errors.forbidden");
    }
    return t("passwordConfirmModal.errorGeneric");
  }

  // ── Eye toggle (Req 5.5 – 5.13) ─────────────────────────────────────────

  function handleEyeToggle(credentialId: number) {
    if (revealedRow?.credentialId === credentialId) {
      maskCurrentRow(); // Req 5.9
      return;
    }
    if (revealedRow !== null) {
      setModal({ type: "alreadyVisible", pendingId: credentialId }); // Req 5.10
      setModalError(undefined);
      return;
    }
    setModal({ type: "revealConfirm", targetId: credentialId }); // Req 5.13
    setModalError(undefined);
  }

  function handleAlreadyVisibleContinue() {
    const pendingId = (modal as { type: "alreadyVisible"; pendingId: number }).pendingId;
    maskCurrentRow();
    setModal({ type: "revealConfirm", targetId: pendingId });
    setModalError(undefined);
  }

  function closeModal() {
    setModal({ type: "none" });
    setModalError(undefined);
  }

  async function handleRevealConfirm(accountPassword: string) {
    const targetId = (modal as { type: "revealConfirm"; targetId: number }).targetId;
    setIsModalLoading(true);
    setModalError(undefined);
    try {
      const response = await apiClient.post<{ password: string }>(
        `/api/credentials/${targetId}/reveal`,
        { account_password: accountPassword }
      );
      setRevealedRow({ credentialId: targetId, plaintext: response.data.password });
      timer.startTimer();
      closeModal();
    } catch (err: unknown) {
      setModalError(modalErrorFor(err));
    } finally {
      setIsModalLoading(false);
    }
  }

  // ── Delete (Req 7.1–7.7) ────────────────────────────────────────────────

  function handleDeleteClick(credential: Credential) {
    setModal({ type: "deleteConfirm", targetId: credential.credential_id, websiteName: credential.website_name });
    setModalError(undefined);
  }

  function handleDeleteConfirm() {
    const m = modal as { type: "deleteConfirm"; targetId: number; websiteName: string };
    setModal({ type: "deletePasswordConfirm", targetId: m.targetId, websiteName: m.websiteName });
    setModalError(undefined);
  }

  async function handleDeletePasswordConfirm(accountPassword: string) {
    const targetId = (modal as { type: "deletePasswordConfirm"; targetId: number }).targetId;
    setIsModalLoading(true);
    setIsDeletingId(targetId);
    setModalError(undefined);
    try {
      await apiClient.delete(`/api/credentials/${targetId}`, { data: { account_password: accountPassword } });
      closeModal();
      if (revealedRow?.credentialId === targetId) maskCurrentRow();
      await loadCredentials();
    } catch (err: unknown) {
      setModalError(modalErrorFor(err));
    } finally {
      setIsModalLoading(false);
      setIsDeletingId(null);
    }
  }

  // ── Pieces shared by the table and the cards ────────────────────────────

  function passwordCell(cred: Credential) {
    const isRevealed = revealedRow?.credentialId === cred.credential_id;
    return isRevealed ? (
      <span className="inline-flex flex-wrap items-center gap-2">
        <span className="font-mono text-gray-900 break-all" onCopy={() => clearLaterIfCopied(revealedRow!.plaintext)}>
          {revealedRow!.plaintext}
        </span>
        <button
          type="button"
          onClick={async () => setCopied((await copySecret(revealedRow!.plaintext)) ? cred.credential_id : null)}
          aria-label={t("credentials.copyPassword", { site: cred.website_name })}
          className="rounded border border-gray-300 px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
        >
          {copied === cred.credential_id ? t("credentials.copied") : t("credentials.copy")}
        </button>
        {timer.secondsRemaining > 0 && (
          <span
            className="text-xs text-gray-400 tabular-nums"
            aria-live="polite"
            aria-label={`${t("visibilityTimer.label")} ${timer.secondsRemaining}s`}
          >
            ({timer.secondsRemaining}s)
          </span>
        )}
      </span>
    ) : (
      <span className="text-gray-400" aria-label={t("credentials.maskedPassword")}>
        {t("credentials.maskedPassword")}
      </span>
    );
  }

  function actions(cred: Credential) {
    const isRevealed = revealedRow?.credentialId === cred.credential_id;
    return (
      <div className="inline-flex items-center gap-1">
        <button
          type="button"
          onClick={() => handleEyeToggle(cred.credential_id)}
          className={`${iconButton} hover:text-indigo-600 hover:bg-indigo-50 focus:ring-indigo-500`}
          aria-label={isRevealed ? t("credentials.hideButton") : t("credentials.revealButton")}
          aria-pressed={isRevealed}
        >
          {isRevealed ? <EyeClosedIcon /> : <EyeOpenIcon />}
        </button>
        <Link
          to={`/credentials/${cred.credential_id}/edit`}
          className={`${iconButton} hover:text-indigo-600 hover:bg-indigo-50 focus:ring-indigo-500`}
          aria-label={`${t("credentials.editButton")} ${cred.website_name}`}
        >
          <EditIcon />
        </Link>
        <button
          type="button"
          onClick={() => handleDeleteClick(cred)}
          disabled={isDeletingId === cred.credential_id}
          title={isDeletingId === cred.credential_id ? t("credentials.deleting") : undefined}
          className={`${iconButton} hover:text-red-600 hover:bg-red-50 focus:ring-red-500 disabled:opacity-40 disabled:cursor-not-allowed`}
          aria-label={`${t("credentials.deleteButton")} ${cred.website_name}`}
        >
          <TrashIcon />
        </button>
      </div>
    );
  }

  const th = "px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const showList = !isLoading && !fetchError && paged.total > 0;

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      <main className="flex-1 px-4 py-8 sm:py-10">
        <div className="mx-auto w-full max-w-5xl">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
            <h1 className="text-2xl font-bold text-gray-900">{t("credentials.pageTitle")}</h1>
            <Link
              to="/credentials/new"
              className={[
                "inline-flex items-center justify-center gap-2 rounded-md",
                "bg-indigo-600 text-white text-sm font-semibold",
                "px-4 py-2 min-h-[44px]",
                "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
                "transition-colors duration-150 whitespace-nowrap",
              ].join(" ")}
            >
              <PlusIcon className="h-4 w-4" />
              {t("credentials.addNew")}
            </Link>
          </div>

          <ListToolbar view={<ViewToggle view={view} onChange={setView} />}>
            <SearchBox
              id="credential-search"
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder={t("credentials.searchPlaceholder")}
            />
            <FilterSelect
              id="credential-login-type"
              label={t("credentials.filterLoginType")}
              value={loginType}
              onChange={(v) => setLoginType(v as LoginType)}
              options={[
                { value: "email", label: t("credentials.loginTypeEmail") },
                { value: "username", label: t("credentials.loginTypeUsername") },
              ]}
            />
          </ListToolbar>

          {fetchError && (
            <div
              role="alert"
              aria-live="assertive"
              className="mb-5 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
            >
              {fetchError}
            </div>
          )}

          {isLoading && (
            <p className="text-sm text-gray-500 mb-4" aria-live="polite">
              {t("common.loading")}
            </p>
          )}

          {!isLoading && !fetchError && credentials.length === 0 && (
            <p className="text-sm text-gray-500" aria-live="polite">
              {t("credentials.noData")}
            </p>
          )}
          {!isLoading && !fetchError && credentials.length > 0 && filtered.length === 0 && (
            <p className="text-sm text-gray-500" aria-live="polite">
              {t("credentials.noResults")}
            </p>
          )}

          {/* Table (Req 5.4, 11.3 — horizontally scrollable) */}
          {showList && view === "list" && (
            <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200 bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className={th}>{t("credentials.tableHeaderWebsite")}</th>
                    <th scope="col" className={th}>{t("credentials.tableHeaderEmailUsername")}</th>
                    <th scope="col" className={th}>{t("credentials.tableHeaderPassword")}</th>
                    <th scope="col" className={`${th} text-right`}>{t("credentials.tableHeaderActions")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paged.pageItems.map((cred) => (
                    <tr key={cred.credential_id} className="hover:bg-gray-50 transition-colors duration-100">
                      <td className="px-4 py-3 text-sm text-gray-900 whitespace-nowrap">{cred.website_name}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">{mask(cred.email_or_username)}</td>
                      <td className="px-4 py-3 text-sm whitespace-nowrap">{passwordCell(cred)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">{actions(cred)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Cards */}
          {showList && view === "grid" && (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {paged.pageItems.map((cred) => (
                <li
                  key={cred.credential_id}
                  className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
                  aria-label={cred.website_name}
                >
                  <p className="truncate text-base font-semibold text-gray-900">{cred.website_name}</p>
                  <p className="truncate text-sm text-gray-600">{mask(cred.email_or_username)}</p>
                  <p className="text-sm">{passwordCell(cred)}</p>
                  <div className="mt-auto flex justify-end border-t border-gray-100 pt-2">{actions(cred)}</div>
                </li>
              ))}
            </ul>
          )}

          {showList && <Pagination paged={paged} id="credentials-pages" />}
        </div>
      </main>

      {modal.type === "alreadyVisible" && (
        <AlreadyVisibleModal onContinue={handleAlreadyVisibleContinue} onCancel={closeModal} />
      )}
      {modal.type === "revealConfirm" && (
        <PasswordConfirmModal
          onConfirm={handleRevealConfirm}
          onCancel={closeModal}
          error={modalError}
          isLoading={isModalLoading}
        />
      )}
      {modal.type === "deleteConfirm" && (
        <ConfirmDeleteModal websiteName={modal.websiteName} onConfirm={handleDeleteConfirm} onCancel={closeModal} />
      )}
      {modal.type === "deletePasswordConfirm" && (
        <PasswordConfirmModal
          onConfirm={handleDeletePasswordConfirm}
          onCancel={closeModal}
          error={modalError}
          isLoading={isModalLoading}
        />
      )}
    </>
  );
}
