import { useState, useEffect, type FormEvent } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import PasswordInput from "../components/PasswordInput";
import PasswordConfirmModal from "../components/PasswordConfirmModal";

// ── Types ────────────────────────────────────────────────────────────────────

interface FormFields {
  website_name: string;
  email_or_username: string;
  password: string;
  is_username_login: boolean;
}

interface FormErrors {
  website_name?: string;
  email_or_username?: string;
  password?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * EditCredentialPage — /credentials/:id/edit
 *
 * Lets an authenticated user edit an existing credential. The page fetches the
 * credential via GET /api/credentials/:id (password comes back as null — not
 * revealed), pre-populates all fields, and on "Update" shows a
 * PasswordConfirmModal before sending PUT /api/credentials/:id.
 *
 * Requirements 6.1–6.9:
 *  6.1   Edit icon visible on each row of the search page (handled in ViewSearchPage).
 *  6.2   Page pre-populated with existing website_name, email/username, and masked password.
 *  6.3   All three fields are editable.
 *  6.4   "Cancel" button navigates back to /credentials without saving.
 *  6.5   "Update" button shows PasswordConfirmModal.
 *  6.6   Incorrect account password → backend returns 401 → error shown in modal.
 *  6.7   Valid update → backend re-encrypts and persists (handled server-side).
 *  6.8   Backend sets modification audit columns (handled server-side).
 *  6.9   Backend writes audit_log UPDATE entry (handled server-side).
 */
export default function EditCredentialPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  // ── Fetch state ─────────────────────────────────────────────────────────

  const [isFetching, setIsFetching] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // ── Form state ──────────────────────────────────────────────────────────

  const [fields, setFields] = useState<FormFields>({
    website_name: "",
    email_or_username: "",
    password: "",
    is_username_login: false,
  });

  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);

  // ── Modal state ─────────────────────────────────────────────────────────

  const [showModal, setShowModal] = useState(false);
  const [modalError, setModalError] = useState<string | undefined>(undefined);
  const [isSaving, setIsSaving] = useState(false);

  // ── Fetch credential on mount (Requirement 6.2) ─────────────────────────

  useEffect(() => {
    if (!id) {
      setFetchError(t("editCredential.errorNotFound"));
      setIsFetching(false);
      return;
    }

    let cancelled = false;

    async function loadCredential() {
      try {
        const response = await apiClient.get<{
          credential_id: number;
          website_name: string;
          email_or_username: string;
          is_username_login: boolean;
          password: null;
        }>(`/api/credentials/${id}`);

        if (!cancelled) {
          const data = response.data;
          setFields({
            website_name: data.website_name,
            email_or_username: data.email_or_username,
            // password arrives as null (no reveal); start as empty so the user
            // must explicitly re-enter it to change it (Req 6.2 — masked field)
            password: "",
            is_username_login: data.is_username_login,
          });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          if (axios.isAxiosError(err)) {
            if (err.response?.status === 404) {
              setFetchError(t("editCredential.errorNotFound"));
            } else if (err.response?.status === 403) {
              setFetchError(t("errors.forbidden"));
            } else {
              setFetchError(t("errors.generic"));
            }
          } else {
            setFetchError(t("errors.generic"));
          }
        }
      } finally {
        if (!cancelled) setIsFetching(false);
      }
    }

    loadCredential();

    return () => {
      cancelled = true;
    };
  }, [id, t]);

  // ── Field helpers ───────────────────────────────────────────────────────

  function handleChange(field: keyof Omit<FormFields, "is_username_login">) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFields((prev) => ({ ...prev, [field]: e.target.value }));
      setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
    };
  }

  function handleCheckboxChange(e: React.ChangeEvent<HTMLInputElement>) {
    const checked = e.target.checked;
    setFields((prev) => ({
      ...prev,
      is_username_login: checked,
      // Clear value when switching modes to avoid stale data
      email_or_username: "",
    }));
    setFieldErrors((prev) => ({ ...prev, email_or_username: undefined }));
  }

  // ── Client-side validation ──────────────────────────────────────────────

  function validate(): FormErrors {
    const errors: FormErrors = {};

    // website_name — required, must start with alphanumeric (Requirement 6.3 / 4.2)
    const website = fields.website_name.trim();
    if (!website) {
      errors.website_name = t("errors.validationError");
    } else if (!/^[a-zA-Z0-9]/.test(website)) {
      errors.website_name = t("errors.validationError");
    }

    // email_or_username — required regardless of mode
    const emailUsername = fields.email_or_username.trim();
    if (!emailUsername) {
      errors.email_or_username = t("errors.validationError");
    } else if (!fields.is_username_login) {
      // Basic RFC 5321 format check on the client (server enforces strictly)
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailUsername)) {
        errors.email_or_username = t("signup.errorInvalidEmail");
      }
    }

    // password — required (user must re-enter to update; Req 6.3)
    if (!fields.password) {
      errors.password = t("errors.validationError");
    }

    return errors;
  }

  // ── Form submit → open modal (Requirement 6.5) ─────────────────────────

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setApiError(null);

    const errors = validate();
    const hasErrors = Object.values(errors).some(Boolean);
    if (hasErrors) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setModalError(undefined);
    setShowModal(true);
  }

  // ── Modal confirm → PUT /api/credentials/:id (Req 6.5–6.9) ────────────

  async function handleModalConfirm(accountPassword: string) {
    setIsSaving(true);
    setModalError(undefined);

    try {
      await apiClient.put(`/api/credentials/${id}`, {
        website_name: fields.website_name.trim(),
        email_or_username: fields.email_or_username.trim(),
        is_username_login: fields.is_username_login,
        password: fields.password,
        account_password: accountPassword,
      });

      // 200 OK — navigate to the credentials list
      navigate("/credentials", { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;

        if (status === 401) {
          // Wrong account password (Requirement 6.6)
          setModalError(t("passwordConfirmModal.errorWrongPassword"));
        } else if (status === 404) {
          setModalError(t("editCredential.errorNotFound"));
        } else if (status === 422) {
          // Validation error from server (e.g. disposable email domain)
          const detail = err.response?.data?.detail;
          if (typeof detail === "string" && detail.toLowerCase().includes("disposable")) {
            setModalError(t("signup.errorDisposableEmail"));
          } else if (typeof detail === "string" && detail.toLowerCase().includes("email")) {
            setModalError(t("signup.errorInvalidEmail"));
          } else {
            setModalError(t("editCredential.errorUpdateFailed"));
          }
        } else {
          setModalError(t("editCredential.errorUpdateFailed"));
        }
      } else {
        setModalError(t("editCredential.errorUpdateFailed"));
      }
    } finally {
      setIsSaving(false);
    }
  }

  function handleModalCancel() {
    setShowModal(false);
    setModalError(undefined);
  }

  // ── Render ──────────────────────────────────────────────────────────────

  // Loading state
  if (isFetching) {
    return (
      <main className="min-h-screen bg-gray-50 px-4 py-10 sm:py-14">
        <div className="mx-auto w-full max-w-lg">
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("common.loading")}
          </p>
        </div>
      </main>
    );
  }

  // Fetch error state
  if (fetchError) {
    return (
      <main className="min-h-screen bg-gray-50 px-4 py-10 sm:py-14">
        <div className="mx-auto w-full max-w-lg">
          <div
            role="alert"
            aria-live="assertive"
            className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-5"
          >
            {fetchError}
          </div>
          <Link
            to="/credentials"
            className="text-sm text-indigo-600 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {t("editCredential.cancelButton")}
          </Link>
        </div>
      </main>
    );
  }

  return (
    <>
      <main className="min-h-screen bg-gray-50 px-4 py-10 sm:py-14">
        <div className="mx-auto w-full max-w-lg">
          {/* Card */}
          <div className="bg-white rounded-2xl shadow-md px-6 py-8 sm:px-10 sm:py-10">
            {/* Page heading */}
            <h1 className="text-2xl font-bold text-gray-900 mb-8">
              {t("editCredential.pageTitle")}
            </h1>

            {/* API-level error banner */}
            {apiError && (
              <div
                role="alert"
                aria-live="assertive"
                className="mb-5 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
              >
                {apiError}
              </div>
            )}

            <form
              onSubmit={handleSubmit}
              noValidate
              aria-label={t("editCredential.pageTitle")}
            >
              {/* ── Website Name ── */}
              <div className="mb-5">
                <label
                  htmlFor="edit-website"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t("editCredential.websiteLabel")}
                  <span aria-hidden="true" className="ml-1 text-red-500">
                    *
                  </span>
                </label>
                <input
                  id="edit-website"
                  type="text"
                  autoComplete="off"
                  value={fields.website_name}
                  onChange={handleChange("website_name")}
                  placeholder={t("editCredential.websitePlaceholder")}
                  aria-required="true"
                  aria-describedby={
                    fieldErrors.website_name ? "edit-website-error" : undefined
                  }
                  className={[
                    "block w-full rounded-md border px-3 py-2",
                    "text-gray-900 placeholder-gray-400 text-sm",
                    "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                    "min-h-[44px] md:min-h-0",
                    fieldErrors.website_name
                      ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                      : "border-gray-300",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                />
                {fieldErrors.website_name && (
                  <p
                    id="edit-website-error"
                    role="alert"
                    className="mt-1 text-sm text-red-600"
                  >
                    {fieldErrors.website_name}
                  </p>
                )}
              </div>

              {/* ── Username-login toggle checkbox (Requirement 4.4 / 6.3) ── */}
              <div className="mb-5">
                <label className="inline-flex items-start gap-3 cursor-pointer select-none">
                  <input
                    id="edit-username-login"
                    type="checkbox"
                    checked={fields.is_username_login}
                    onChange={handleCheckboxChange}
                    className={[
                      "mt-0.5 h-4 w-4 rounded border-gray-300",
                      "text-indigo-600 focus:ring-indigo-500",
                      "min-h-[44px] min-w-[44px] p-0 md:min-h-0 md:min-w-0",
                    ].join(" ")}
                  />
                  <span className="text-sm text-gray-700">
                    {t("editCredential.usernameLoginCheckbox")}
                  </span>
                </label>
              </div>

              {/* ── Email OR Username field (Requirement 6.3) ── */}
              <div className="mb-5">
                {fields.is_username_login ? (
                  /* Username field */
                  <>
                    <label
                      htmlFor="edit-username"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t("editCredential.usernameLabel")}
                      <span aria-hidden="true" className="ml-1 text-red-500">
                        *
                      </span>
                    </label>
                    <input
                      id="edit-username"
                      type="text"
                      autoComplete="username"
                      value={fields.email_or_username}
                      onChange={handleChange("email_or_username")}
                      placeholder={t("editCredential.usernamePlaceholder")}
                      aria-required="true"
                      aria-describedby={
                        fieldErrors.email_or_username
                          ? "edit-emailusername-error"
                          : undefined
                      }
                      className={[
                        "block w-full rounded-md border px-3 py-2",
                        "text-gray-900 placeholder-gray-400 text-sm",
                        "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                        "min-h-[44px] md:min-h-0",
                        fieldErrors.email_or_username
                          ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                          : "border-gray-300",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    />
                  </>
                ) : (
                  /* Email field */
                  <>
                    <label
                      htmlFor="edit-email"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t("editCredential.emailLabel")}
                      <span aria-hidden="true" className="ml-1 text-red-500">
                        *
                      </span>
                    </label>
                    <input
                      id="edit-email"
                      type="email"
                      autoComplete="email"
                      value={fields.email_or_username}
                      onChange={handleChange("email_or_username")}
                      placeholder={t("editCredential.emailPlaceholder")}
                      aria-required="true"
                      aria-describedby={
                        fieldErrors.email_or_username
                          ? "edit-emailusername-error"
                          : undefined
                      }
                      className={[
                        "block w-full rounded-md border px-3 py-2",
                        "text-gray-900 placeholder-gray-400 text-sm",
                        "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                        "min-h-[44px] md:min-h-0",
                        fieldErrors.email_or_username
                          ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                          : "border-gray-300",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                    />
                  </>
                )}
                {fieldErrors.email_or_username && (
                  <p
                    id="edit-emailusername-error"
                    role="alert"
                    className="mt-1 text-sm text-red-600"
                  >
                    {fieldErrors.email_or_username}
                  </p>
                )}
              </div>

              {/* ── Credential Password (Requirement 6.3) ── */}
              <div className="mb-8">
                <div className="relative">
                  <PasswordInput
                    id="edit-password"
                    label={`${t("editCredential.passwordLabel")} *`}
                    placeholder={t("editCredential.passwordPlaceholder")}
                    autoComplete="new-password"
                    value={fields.password}
                    onChange={handleChange("password")}
                    aria-required="true"
                    error={fieldErrors.password}
                  />
                </div>
              </div>

              {/* ── Actions (Requirement 6.4 & 6.5) ── */}
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                {/* Cancel — navigates back without saving (Requirement 6.4) */}
                <Link
                  to="/credentials"
                  className={[
                    "inline-flex items-center justify-center rounded-md",
                    "border border-gray-300 text-gray-700 text-sm font-medium",
                    "px-4 py-2 min-h-[44px]",
                    "hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                    "transition-colors duration-150",
                  ].join(" ")}
                >
                  {t("editCredential.cancelButton")}
                </Link>

                {/* Update — shows PasswordConfirmModal (Requirement 6.5) */}
                <button
                  type="submit"
                  className={[
                    "inline-flex items-center justify-center rounded-md",
                    "bg-indigo-600 text-white text-sm font-semibold",
                    "px-4 py-2 min-h-[44px]",
                    "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
                    "transition-colors duration-150",
                  ].join(" ")}
                >
                  {t("editCredential.updateButton")}
                </button>
              </div>
            </form>
          </div>
        </div>
      </main>

      {/* ── Password Confirmation Modal (Requirement 6.5–6.6) ── */}
      {showModal && (
        <PasswordConfirmModal
          onConfirm={handleModalConfirm}
          onCancel={handleModalCancel}
          error={modalError}
          isLoading={isSaving}
        />
      )}
    </>
  );
}
