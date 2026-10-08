import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import PasswordInput from "../components/PasswordInput";

// ── Types ────────────────────────────────────────────────────────────────────

interface FormFields {
  username: string;
  email: string;
  password: string;
  password_confirmation: string;
}

interface FormErrors {
  username?: string;
  email?: string;
  password?: string[];
  password_confirmation?: string;
}

// ── Password rule helpers ────────────────────────────────────────────────────

interface PasswordRule {
  key: string;
  label: string;
  test: (pw: string) => boolean;
}

function buildPasswordRules(t: (key: string) => string): PasswordRule[] {
  return [
    {
      key: "minLength",
      label: t("passwordRules.minLength"),
      test: (pw) => pw.length >= 12,
    },
    {
      key: "uppercase",
      label: t("passwordRules.uppercase"),
      test: (pw) => /[A-Z]/.test(pw),
    },
    {
      key: "lowercase",
      label: t("passwordRules.lowercase"),
      test: (pw) => /[a-z]/.test(pw),
    },
    {
      key: "digit",
      label: t("passwordRules.digit"),
      test: (pw) => /[0-9]/.test(pw),
    },
    {
      key: "symbol",
      label: t("passwordRules.symbol"),
      test: (pw) => /[@$!]/.test(pw),
    },
  ];
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * SignUpPage — /signup
 *
 * Renders a registration form (username, email, password, password_confirmation).
 * Validates password strength client-side, displaying per-rule errors via t().
 * On successful POST /api/auth/register (201) redirects to /login.
 *
 * Requirements 1.1–1.8:
 *  1.1  Sign-up page accessible from the login page.
 *  1.2  Collects username, email, and password.
 *  1.3  Requires password_confirmation that matches password exactly.
 *  1.4  Mismatch → field-level error, prevent account creation.
 *  1.5  Enforces minimum 12 chars, uppercase, lowercase, digit, symbol.
 *  1.6  Unmet rules → descriptive error listing each unmet rule.
 *  1.7  Backend hashes password (handled server-side).
 *  1.8  Backend sets audit columns (handled server-side).
 */
export default function SignUpPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const passwordRules = buildPasswordRules(t);

  const [fields, setFields] = useState<FormFields>({
    username: "",
    email: "",
    password: "",
    password_confirmation: "",
  });

  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // ── Field change handler ────────────────────────────────────────────────

  function handleChange(field: keyof FormFields) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFields((prev) => ({ ...prev, [field]: e.target.value }));
    };
  }

  // ── Validation ──────────────────────────────────────────────────────────

  function validate(): FormErrors {
    const errors: FormErrors = {};

    // Username
    if (!fields.username.trim()) {
      errors.username = t("login.errorUsernameRequired");
    }

    // Email – basic format check
    if (!fields.email.trim()) {
      errors.email = t("signup.errorInvalidEmail");
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email.trim())) {
      errors.email = t("signup.errorInvalidEmail");
    }

    // Password strength (Requirement 1.5 & 1.6)
    const unmetRules = passwordRules
      .filter((rule) => !rule.test(fields.password))
      .map((rule) => rule.label);

    if (fields.password === "") {
      // No password at all — show all rules as requirements
      errors.password = passwordRules.map((r) => r.label);
    } else if (unmetRules.length > 0) {
      errors.password = unmetRules;
    }

    // Password confirmation (Requirement 1.3 & 1.4)
    if (!fields.password_confirmation) {
      errors.password_confirmation = t("signup.errorPasswordMismatch");
    } else if (fields.password !== fields.password_confirmation) {
      errors.password_confirmation = t("signup.errorPasswordMismatch");
    }

    return errors;
  }

  // ── Submit handler ──────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setApiError(null);

    const errors = validate();
    const hasErrors =
      errors.username !== undefined ||
      errors.email !== undefined ||
      (errors.password !== undefined && errors.password.length > 0) ||
      errors.password_confirmation !== undefined;

    if (hasErrors) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});

    setIsSubmitting(true);
    try {
      await apiClient.post("/api/auth/register", {
        username: fields.username.trim(),
        email: fields.email.trim(),
        password: fields.password,
        password_confirmation: fields.password_confirmation,
      });

      // 201 Created — redirect to /login (Requirement 1.1)
      navigate("/login", { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        const detail = err.response?.data?.detail as string | undefined;

        if (status === 409) {
          // Conflict — duplicate username or email
          if (detail?.toLowerCase().includes("email")) {
            setApiError(t("signup.errorDuplicateEmail"));
          } else {
            setApiError(t("signup.errorDuplicateUsername"));
          }
        } else if (status === 422) {
          setApiError(t("signup.errorInvalidEmail"));
        } else {
          setApiError(t("errors.serverError"));
        }
      } else {
        setApiError(t("errors.serverError"));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-md px-8 py-10">
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-8">
            {t("signup.title")}
          </h1>

          <form
            onSubmit={handleSubmit}
            noValidate
            aria-label={t("signup.title")}
          >
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

            {/* Username field */}
            <div className="mb-5">
              <label
                htmlFor="signup-username"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t("signup.usernameLabel")}
              </label>
              <input
                id="signup-username"
                type="text"
                autoComplete="username"
                value={fields.username}
                onChange={handleChange("username")}
                placeholder={t("signup.usernamePlaceholder")}
                aria-required="true"
                aria-describedby={
                  fieldErrors.username ? "signup-username-error" : undefined
                }
                className={[
                  "block w-full rounded-md border px-3 py-2",
                  "text-gray-900 placeholder-gray-400 text-sm",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                  "min-h-[44px] md:min-h-0",
                  fieldErrors.username
                    ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                    : "border-gray-300",
                ]
                  .filter(Boolean)
                  .join(" ")}
              />
              {fieldErrors.username && (
                <p
                  id="signup-username-error"
                  role="alert"
                  className="mt-1 text-sm text-red-600"
                >
                  {fieldErrors.username}
                </p>
              )}
            </div>

            {/* Email field */}
            <div className="mb-5">
              <label
                htmlFor="signup-email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t("signup.emailLabel")}
              </label>
              <input
                id="signup-email"
                type="email"
                autoComplete="email"
                value={fields.email}
                onChange={handleChange("email")}
                placeholder={t("signup.emailPlaceholder")}
                aria-required="true"
                aria-describedby={
                  fieldErrors.email ? "signup-email-error" : undefined
                }
                className={[
                  "block w-full rounded-md border px-3 py-2",
                  "text-gray-900 placeholder-gray-400 text-sm",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                  "min-h-[44px] md:min-h-0",
                  fieldErrors.email
                    ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                    : "border-gray-300",
                ]
                  .filter(Boolean)
                  .join(" ")}
              />
              {fieldErrors.email && (
                <p
                  id="signup-email-error"
                  role="alert"
                  className="mt-1 text-sm text-red-600"
                >
                  {fieldErrors.email}
                </p>
              )}
            </div>

            {/* Password field with strength rules */}
            <div className="mb-5">
              <PasswordInput
                id="signup-password"
                label={t("signup.passwordLabel")}
                placeholder={t("signup.passwordPlaceholder")}
                autoComplete="new-password"
                value={fields.password}
                onChange={handleChange("password")}
                aria-required="true"
              />
              {/* Per-rule error list (Requirement 1.5 & 1.6) */}
              {fieldErrors.password && fieldErrors.password.length > 0 && (
                <ul
                  id="signup-password-rules"
                  role="alert"
                  aria-label={t("passwordRules.title")}
                  className="mt-2 space-y-1"
                >
                  {fieldErrors.password.map((msg) => (
                    <li
                      key={msg}
                      className="flex items-start gap-1.5 text-sm text-red-600"
                    >
                      {/* Bullet */}
                      <span aria-hidden="true" className="mt-0.5 shrink-0">
                        ✕
                      </span>
                      {msg}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Password confirmation field */}
            <div className="mb-6">
              <PasswordInput
                id="signup-password-confirmation"
                label={t("signup.passwordConfirmLabel")}
                placeholder={t("signup.passwordConfirmPlaceholder")}
                autoComplete="new-password"
                value={fields.password_confirmation}
                onChange={handleChange("password_confirmation")}
                aria-required="true"
                error={fieldErrors.password_confirmation}
              />
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting}
              className={[
                "w-full flex items-center justify-center rounded-md",
                "bg-indigo-600 text-white font-semibold text-sm",
                "px-4 py-3 min-h-[44px]",
                "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
                "transition-colors duration-150",
                isSubmitting ? "opacity-60 cursor-not-allowed" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {isSubmitting ? t("common.loading") : t("signup.submitButton")}
            </button>
          </form>

          {/* Log-in link */}
          <p className="mt-6 text-center text-sm text-gray-600">
            {t("signup.hasAccount")}{" "}
            <Link
              to="/login"
              className="font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus:underline"
            >
              {t("signup.loginLink")}
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
