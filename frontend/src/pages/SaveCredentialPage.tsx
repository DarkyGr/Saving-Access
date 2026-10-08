import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
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
 * SaveCredentialPage — /credentials/new
 *
 * Lets an authenticated user save a new credential (website name, email or
 * username, and a credential password). Sensitive operations require the user
 * to re-enter their account password in a PasswordConfirmModal before the
 * POST is sent to the backend.
 *
 * Requirements 4.1–4.13:
 *  4.1   Page accessible to authenticated users with the required Profile permission.
 *  4.2   Mandatory website_name field, alphanumeric.
 *  4.3   Mandatory email field by default.
 *  4.4   is_username_login checkbox hides email, shows mandatory username field.
 *  4.5   Credential password field is masked by default with an Eye_Toggle.
 *  4.6/7 Eye_Toggle shows / hides the credential password field.
 *  4.8   PasswordConfirmModal shown before the save request is sent.
 *  4.9   Incorrect account password → backend returns 401 → error shown in modal.
 *  4.10  Backend encrypts credential password (handled server-side).
 *  4.11  Backend records audit columns on creation (handled server-side).
 *  4.12  Backend writes audit_log INSERT entry (handled server-side).
 *  4.13  Email validated against RFC 5321; disposable domains rejected server-side.
 */
export default function SaveCredentialPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

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

  // ── Field helpers ───────────────────────────────────────────────────────

  function handleChange(field: keyof Omit<FormFields, "is_username_login">) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFields((prev) => ({ ...prev, [field]: e.target.value }));
      // Clear the field error as the user types
      setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
    };
  }

  function handleCheckboxChange(e: React.ChangeEvent<HTMLInputElement>) {
    const checked = e.target.checked;
    setFields((prev) => ({
      ...prev,
      is_username_login: checked,
      // Clear the email/username value when switching modes to avoid stale data
      email_or_username: "",
    }));
    setFieldErrors((prev) => ({ ...prev, email_or_username: undefined }));
  }

  // ── Client-side validation ──────────────────────────────────────────────

  function validate(): FormErrors {
    const errors: FormErrors = {};

    // website_name — required, alphanumeric (letters, digits, spaces, hyphens,
    // dots all reasonably expected for a site name; pure non-alphanumeric is rejected)
    const website = fields.website_name.trim();
    if (!website) {
      errors.website_name = t("errors.validationError");
    } else if (!/^[a-zA-Z0-9]/.test(website)) {
      // Must start with an alphanumeric character (Requirement 4.2)
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

    // password — required
    if (!fields.password) {
      errors.password = t("errors.validationError");
    }

    return errors;
  }

  // ── Form submit → open modal ────────────────────────────────────────────

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

  // ── Modal confirm → POST /api/credentials ──────────────────────────────

  async function handleModalConfirm(accountPassword: string) {
    setIsSaving(true);
    setModalError(undefined);

    try {
      await apiClient.post("/api/credentials", {
        website_name: fields.website_name.trim(),
        email_or_username: fields.email_or_username.trim(),
        is_username_login: fields.is_username_login,
        password: fields.password,
        account_password: accountPassword,
      });

      // 201 Created — navigate to the credentials list
      navigate("/credentials", { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;

        if (status === 401) {
          // Wrong account password
          setModalError(t("passwordConfirmModal.errorWrongPassword"));
        } else if (status === 422) {
          // Validation error from server (e.g. disposable email domain)
          const detail = err.response?.data?.detail;
          if (typeof detail === "string" && detail.toLowerCase().includes("disposable")) {
            setModalError(t("signup.errorDisposableEmail"));
          } else if (typeof detail === "string" && detail.toLowerCase().includes("email")) {
            setModalError(t("signup.errorInvalidEmail"));
          } else {
            setModalError(t("saveCredential.errorSaveFailed"));
          }
        } else {
          setModalError(t("saveCredential.errorSaveFailed"));
        }
      } else {
        setModalError(t("saveCredential.errorSaveFailed"));
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

  return (
    <>
      <main className="min-h-screen bg-gray-50 px-4 py-10 sm:py-14">
        <div className="mx-auto w-full max-w-lg">
          {/* Card */}
          <div className="bg-white rounded-2xl shadow-md px-6 py-8 sm:px-10 sm:py-10">
            {/* Page heading */}
            <h1 className="text-2xl font-bold text-gray-900 mb-8">
              {t("saveCredential.pageTitle")}
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
              aria-label={t("saveCredential.pageTitle")}
            >
              {/* ── Website Name ── */}
              <div className="mb-5">
                <label
                  htmlFor="save-website"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t("saveCredential.websiteLabel")}
                  <span aria-hidden="true" className="ml-1 text-red-500">
                    *
                  </span>
                </label>
                <input
                  id="save-website"
                  type="text"
                  autoComplete="off"
                  value={fields.website_name}
                  onChange={handleChange("website_name")}
                  placeholder={t("saveCredential.websitePlaceholder")}
                  aria-required="true"
                  aria-describedby={
                    fieldErrors.website_name ? "save-website-error" : undefined
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
                    id="save-website-error"
                    role="alert"
                    className="mt-1 text-sm text-red-600"
                  >
                    {fieldErrors.website_name}
                  </p>
                )}
              </div>

              {/* ── Username-login toggle checkbox (Requirement 4.4) ── */}
              <div className="mb-5">
                <label className="inline-flex items-start gap-3 cursor-pointer select-none">
                  <input
                    id="save-username-login"
                    type="checkbox"
                    checked={fields.is_username_login}
                    onChange={handleCheckboxChange}
                    className={[
                      "mt-0.5 h-4 w-4 rounded border-gray-300",
                      "text-indigo-600 focus:ring-indigo-500",
                      /* touch-friendly padding on mobile */
                      "min-h-[44px] min-w-[44px] p-0 md:min-h-0 md:min-w-0",
                    ].join(" ")}
                  />
                  <span className="text-sm text-gray-700">
                    {t("saveCredential.usernameLoginCheckbox")}
                  </span>
                </label>
              </div>

              {/* ── Email OR Username field (Requirement 4.3 & 4.4) ── */}
              <div className="mb-5">
                {fields.is_username_login ? (
                  /* Username field */
                  <>
                    <label
                      htmlFor="save-username"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t("saveCredential.usernameLabel")}
                      <span aria-hidden="true" className="ml-1 text-red-500">
                        *
                      </span>
                    </label>
                    <input
                      id="save-username"
                      type="text"
                      autoComplete="username"
                      value={fields.email_or_username}
                      onChange={handleChange("email_or_username")}
                      placeholder={t("saveCredential.usernamePlaceholder")}
                      aria-required="true"
                      aria-describedby={
                        fieldErrors.email_or_username
                          ? "save-emailusername-error"
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
                      htmlFor="save-email"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      {t("saveCredential.emailLabel")}
                      <span aria-hidden="true" className="ml-1 text-red-500">
                        *
                      </span>
                    </label>
                    <input
                      id="save-email"
                      type="email"
                      autoComplete="email"
                      value={fields.email_or_username}
                      onChange={handleChange("email_or_username")}
                      placeholder={t("saveCredential.emailPlaceholder")}
                      aria-required="true"
                      aria-describedby={
                        fieldErrors.email_or_username
                          ? "save-emailusername-error"
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
                    id="save-emailusername-error"
                    role="alert"
                    className="mt-1 text-sm text-red-600"
                  >
                    {fieldErrors.email_or_username}
                  </p>
                )}
              </div>

              {/* ── Credential Password (Requirement 4.5–4.7) ── */}
              <div className="mb-8">
                {/* Wrap with a div so we can append the required asterisk via CSS label */}
                <div className="relative">
                  <PasswordInput
                    id="save-password"
                    label={`${t("saveCredential.passwordLabel")} *`}
                    placeholder={t("saveCredential.passwordPlaceholder")}
                    autoComplete="new-password"
                    value={fields.password}
                    onChange={handleChange("password")}
                    aria-required="true"
                    error={fieldErrors.password}
                  />
                </div>
              </div>

              {/* ── Actions ── */}
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
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
                  {t("saveCredential.cancelButton")}
                </Link>

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
                  {t("saveCredential.submitButton")}
                </button>
              </div>
            </form>
          </div>
        </div>
      </main>

      {/* ── Password Confirmation Modal (Requirement 4.8–4.9) ── */}
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
