import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useVisibilityTimer } from "../hooks/useVisibilityTimer";
import PasswordConfirmModal from "../components/PasswordConfirmModal";
import AlreadyVisibleModal from "../components/AlreadyVisibleModal";
import ConfirmDeleteModal from "../components/ConfirmDeleteModal";

// ── Types ────────────────────────────────────────────────────────────────────

interface Credential {
  credential_id: number;
  website_name: string;
  email_or_username: string;
  is_username_login: boolean;
  /** Always null from list endpoint; filled in by the reveal flow */
  password: string | null;
}

// ── Modal states ─────────────────────────────────────────────────────────────

type ModalState =
  | { type: "none" }
  | { type: "alreadyVisible"; pendingId: number }
  | { type: "revealConfirm"; targetId: number }
  | { type: "deleteConfirm"; targetId: number; websiteName: string }
  | { type: "deletePasswordConfirm"; targetId: number; websiteName: string };

// ── Per-row reveal state ──────────────────────────────────────────────────────

interface RevealedRow {
  credentialId: number;
  plaintext: string;
}

// ── Eye toggle icon ───────────────────────────────────────────────────────────

function EyeOpenIcon() {
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
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeClosedIcon() {
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
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function EditIcon() {
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
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function TrashIcon() {
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
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * ViewSearchPage — /credentials
 *
 * Main page for viewing and searching saved credentials.
 *
 * Requirements 5.1–5.14, 7.1–7.7:
 *  5.1  Page accessible to authenticated users with the required Profile permission.
 *  5.2  Search input filters by website_name or email (case-insensitive partial match).
 *  5.3  Backend returns only current user's credentials.
 *  5.4  Password column always masked by default.
 *  5.5  Eye_Toggle opens PasswordConfirmModal.
 *  5.6  On correct password, decrypt and display in row.
 *  5.7  Start 60-second Visibility_Timer per row.
 *  5.8  Timer expiry auto-masks password.
 *  5.9  Manual click on revealed eye immediately masks and stops timer.
 *  5.10 If another password is visible, show AlreadyVisibleModal.
 *  5.11 AlreadyVisibleModal "Continue" hides current, proceeds to new reveal.
 *  5.12 AlreadyVisibleModal "Cancel" closes without revealing.
 *  5.13 PasswordConfirmModal always shown on Eye_Toggle click.
 *  5.14 Backend logs SELECT audit entry (server-side).
 *  7.1  Delete icon present on each row.
 *  7.2  Delete icon opens ConfirmDeleteModal.
 *  7.3  ConfirmDeleteModal "Cancel" closes without deleting.
 *  7.4  ConfirmDeleteModal "Delete" opens PasswordConfirmModal.
 *  7.5  Incorrect account password → backend rejects delete (401 shown).
 *  7.6  Valid delete → backend removes credential; list refreshed.
 *  7.7  Backend logs DELETE audit entry (server-side).
 */
export default function ViewSearchPage() {
  const { t } = useTranslation();

  // ── Credentials list state ──────────────────────────────────────────────

  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // ── Reveal state ────────────────────────────────────────────────────────
  // Only one row can have a revealed password at a time (Req 5.10).

  const [revealedRow, setRevealedRow] = useState<RevealedRow | null>(null);
  const timer = useVisibilityTimer(60_000);

  // When the timer expires it sets isVisible = false, so we sync revealedRow
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

  // ── Debounced search ────────────────────────────────────────────────────

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchCredentials = useCallback(async (query: string) => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const params = query.trim() ? { q: query.trim() } : {};
      const response = await apiClient.get<Credential[]>("/api/credentials", {
        params,
      });
      setCredentials(response.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        // The response interceptor in apiClient handles redirect to /login.
        // Nothing further needed here.
        return;
      }
      setFetchError(t("errors.generic"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  // Initial load
  useEffect(() => {
    fetchCredentials("");
  }, [fetchCredentials]);

  // Debounce search input
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchQuery(value);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchCredentials(value);
    }, 300);
  };

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // ── Helpers ─────────────────────────────────────────────────────────────

  function maskCurrentRow() {
    timer.stopTimer();
    setRevealedRow(null);
  }

  // ── Eye toggle logic (Req 5.5 – 5.13) ──────────────────────────────────

  function handleEyeToggle(credentialId: number) {
    // Req 5.9 — manual click on already-open eye immediately masks
    if (revealedRow?.credentialId === credentialId) {
      maskCurrentRow();
      return;
    }

    // Req 5.10 — another row is currently visible → show AlreadyVisibleModal
    if (revealedRow !== null) {
      setModal({ type: "alreadyVisible", pendingId: credentialId });
      setModalError(undefined);
      return;
    }

    // Req 5.13 — always show PasswordConfirmModal
    setModal({ type: "revealConfirm", targetId: credentialId });
    setModalError(undefined);
  }

  // AlreadyVisibleModal "Continue" (Req 5.11)
  function handleAlreadyVisibleContinue() {
    const modal_ = modal as { type: "alreadyVisible"; pendingId: number };
    const pendingId = modal_.pendingId;
    maskCurrentRow();
    setModal({ type: "revealConfirm", targetId: pendingId });
    setModalError(undefined);
  }

  // AlreadyVisibleModal "Cancel" (Req 5.12)
  function handleAlreadyVisibleCancel() {
    setModal({ type: "none" });
    setModalError(undefined);
  }

  // PasswordConfirmModal confirm for reveal (Req 5.5–5.7)
  async function handleRevealConfirm(accountPassword: string) {
    const modal_ = modal as { type: "revealConfirm"; targetId: number };
    const targetId = modal_.targetId;

    setIsModalLoading(true);
    setModalError(undefined);

    try {
      const response = await apiClient.post<{ password: string }>(
        `/api/credentials/${targetId}/reveal`,
        { account_password: accountPassword }
      );

      const plaintext = response.data.password;
      setRevealedRow({ credentialId: targetId, plaintext });
      timer.startTimer();
      setModal({ type: "none" });
      setModalError(undefined);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        if (status === 401) {
          setModalError(t("passwordConfirmModal.errorWrongPassword"));
        } else if (status === 403) {
          setModalError(t("errors.forbidden"));
        } else {
          setModalError(t("passwordConfirmModal.errorGeneric"));
        }
      } else {
        setModalError(t("passwordConfirmModal.errorGeneric"));
      }
    } finally {
      setIsModalLoading(false);
    }
  }

  function handleRevealCancel() {
    setModal({ type: "none" });
    setModalError(undefined);
  }

  // ── Delete flow (Req 7.1–7.7) ───────────────────────────────────────────

  function handleDeleteClick(credential: Credential) {
    setModal({
      type: "deleteConfirm",
      targetId: credential.credential_id,
      websiteName: credential.website_name,
    });
    setModalError(undefined);
  }

  // ConfirmDeleteModal "Delete" → show PasswordConfirmModal (Req 7.4)
  function handleDeleteConfirm() {
    const modal_ = modal as {
      type: "deleteConfirm";
      targetId: number;
      websiteName: string;
    };
    setModal({
      type: "deletePasswordConfirm",
      targetId: modal_.targetId,
      websiteName: modal_.websiteName,
    });
    setModalError(undefined);
  }

  // ConfirmDeleteModal "Cancel" (Req 7.3)
  function handleDeleteModalCancel() {
    setModal({ type: "none" });
    setModalError(undefined);
  }

  // PasswordConfirmModal confirm for delete (Req 7.4–7.6)
  async function handleDeletePasswordConfirm(accountPassword: string) {
    const modal_ = modal as {
      type: "deletePasswordConfirm";
      targetId: number;
      websiteName: string;
    };
    const targetId = modal_.targetId;

    setIsModalLoading(true);
    setIsDeletingId(targetId);
    setModalError(undefined);

    try {
      await apiClient.delete(`/api/credentials/${targetId}`, {
        data: { account_password: accountPassword },
      });

      // Req 7.6 — success (204) → close modal and refresh list
      setModal({ type: "none" });
      setModalError(undefined);

      // If the deleted row was the currently revealed one, clear it
      if (revealedRow?.credentialId === targetId) {
        maskCurrentRow();
      }

      await fetchCredentials(searchQuery);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        if (status === 401) {
          setModalError(t("passwordConfirmModal.errorWrongPassword"));
        } else if (status === 403) {
          setModalError(t("errors.forbidden"));
        } else {
          setModalError(t("passwordConfirmModal.errorGeneric"));
        }
      } else {
        setModalError(t("passwordConfirmModal.errorGeneric"));
      }
    } finally {
      setIsModalLoading(false);
      setIsDeletingId(null);
    }
  }

  function handleDeletePasswordCancel() {
    setModal({ type: "none" });
    setModalError(undefined);
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      <main className="min-h-screen bg-gray-50 px-4 py-8 sm:py-12">
        <div className="mx-auto w-full max-w-5xl">

          {/* ── Header row ── */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
            <h1 className="text-2xl font-bold text-gray-900">
              {t("credentials.pageTitle")}
            </h1>

            <Link
              to="/credentials/new"
              className={[
                "inline-flex items-center justify-center rounded-md",
                "bg-indigo-600 text-white text-sm font-semibold",
                "px-4 py-2 min-h-[44px]",
                "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
                "transition-colors duration-150 whitespace-nowrap",
              ].join(" ")}
            >
              {t("credentials.addNew")}
            </Link>
          </div>

          {/* ── Search input (Req 5.2, debounced 300 ms) ── */}
          <div className="mb-6">
            <label htmlFor="credential-search" className="sr-only">
              {t("credentials.searchPlaceholder")}
            </label>
            <input
              id="credential-search"
              type="search"
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder={t("credentials.searchPlaceholder")}
              autoComplete="off"
              className={[
                "block w-full rounded-md border border-gray-300 px-3 py-2",
                "text-gray-900 placeholder-gray-400 text-sm",
                "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                "min-h-[44px] md:min-h-[40px]",
              ].join(" ")}
            />
          </div>

          {/* ── Error banner ── */}
          {fetchError && (
            <div
              role="alert"
              aria-live="assertive"
              className="mb-5 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
            >
              {fetchError}
            </div>
          )}

          {/* ── Loading indicator ── */}
          {isLoading && (
            <p className="text-sm text-gray-500 mb-4" aria-live="polite">
              {t("common.loading")}
            </p>
          )}

          {/* ── No results ── */}
          {!isLoading && !fetchError && credentials.length === 0 && (
            <p className="text-sm text-gray-500" aria-live="polite">
              {t("credentials.noResults")}
            </p>
          )}

          {/* ── Credentials table (Req 5.4, 11.3 — horizontally scrollable) ── */}
          {!isLoading && credentials.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200 bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {t("credentials.tableHeaderWebsite")}
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {t("credentials.tableHeaderEmailUsername")}
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {t("credentials.tableHeaderPassword")}
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {t("credentials.tableHeaderActions")}
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100">
                  {credentials.map((cred) => {
                    const isRevealed =
                      revealedRow?.credentialId === cred.credential_id;

                    return (
                      <tr
                        key={cred.credential_id}
                        className="hover:bg-gray-50 transition-colors duration-100"
                      >
                        {/* Website */}
                        <td className="px-4 py-3 text-sm text-gray-900 whitespace-nowrap">
                          {cred.website_name}
                        </td>

                        {/* Email / Username */}
                        <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                          {cred.email_or_username}
                        </td>

                        {/* Password (masked or revealed) + timer */}
                        <td className="px-4 py-3 text-sm whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            {isRevealed ? (
                              <>
                                <span className="font-mono text-gray-900">
                                  {revealedRow!.plaintext}
                                </span>
                                {timer.secondsRemaining > 0 && (
                                  <span
                                    className="text-xs text-gray-400 tabular-nums"
                                    aria-live="polite"
                                    aria-label={`${t("visibilityTimer.label")} ${timer.secondsRemaining}s`}
                                  >
                                    ({timer.secondsRemaining}s)
                                  </span>
                                )}
                              </>
                            ) : (
                              <span
                                className="text-gray-400"
                                aria-label={t("credentials.maskedPassword")}
                              >
                                {t("credentials.maskedPassword")}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          <div className="inline-flex items-center gap-1">
                            {/* Eye toggle (Req 5.5) */}
                            <button
                              type="button"
                              onClick={() => handleEyeToggle(cred.credential_id)}
                              className={[
                                "inline-flex items-center justify-center rounded",
                                "p-2 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:p-1.5",
                                "text-gray-500 hover:text-indigo-600 hover:bg-indigo-50",
                                "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1",
                                "transition-colors duration-100",
                              ].join(" ")}
                              aria-label={
                                isRevealed
                                  ? t("credentials.hideButton")
                                  : t("credentials.revealButton")
                              }
                              aria-pressed={isRevealed}
                            >
                              {isRevealed ? <EyeClosedIcon /> : <EyeOpenIcon />}
                            </button>

                            {/* Edit icon → /credentials/:id/edit (Req 6.1–6.2, 21.4) */}
                            <Link
                              to={`/credentials/${cred.credential_id}/edit`}
                              className={[
                                "inline-flex items-center justify-center rounded",
                                "p-2 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:p-1.5",
                                "text-gray-500 hover:text-indigo-600 hover:bg-indigo-50",
                                "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1",
                                "transition-colors duration-100",
                              ].join(" ")}
                              aria-label={`${t("credentials.editButton")} ${cred.website_name}`}
                            >
                              <EditIcon />
                            </Link>

                            {/* Delete icon (Req 7.1–7.2) */}
                            <button
                              type="button"
                              onClick={() => handleDeleteClick(cred)}
                              disabled={isDeletingId === cred.credential_id}
                              className={[
                                "inline-flex items-center justify-center rounded",
                                "p-2 min-w-[44px] min-h-[44px] md:min-w-0 md:min-h-0 md:p-1.5",
                                "text-gray-500 hover:text-red-600 hover:bg-red-50",
                                "focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1",
                                "transition-colors duration-100",
                                "disabled:opacity-40 disabled:cursor-not-allowed",
                              ].join(" ")}
                              aria-label={`${t("credentials.deleteButton")} ${cred.website_name}`}
                            >
                              <TrashIcon />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* ── AlreadyVisibleModal (Req 5.10–5.12) ── */}
      {modal.type === "alreadyVisible" && (
        <AlreadyVisibleModal
          onContinue={handleAlreadyVisibleContinue}
          onCancel={handleAlreadyVisibleCancel}
        />
      )}

      {/* ── PasswordConfirmModal for reveal (Req 5.5, 5.13) ── */}
      {modal.type === "revealConfirm" && (
        <PasswordConfirmModal
          onConfirm={handleRevealConfirm}
          onCancel={handleRevealCancel}
          error={modalError}
          isLoading={isModalLoading}
        />
      )}

      {/* ── ConfirmDeleteModal (Req 7.2–7.3) ── */}
      {modal.type === "deleteConfirm" && (
        <ConfirmDeleteModal
          websiteName={modal.websiteName}
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteModalCancel}
        />
      )}

      {/* ── PasswordConfirmModal for delete (Req 7.4–7.5) ── */}
      {modal.type === "deletePasswordConfirm" && (
        <PasswordConfirmModal
          onConfirm={handleDeletePasswordConfirm}
          onCancel={handleDeletePasswordCancel}
          error={modalError}
          isLoading={isModalLoading}
        />
      )}
    </>
  );
}
