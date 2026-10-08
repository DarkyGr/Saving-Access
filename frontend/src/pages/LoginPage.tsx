import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";
import PasswordInput from "../components/PasswordInput";

// ── Types ────────────────────────────────────────────────────────────────────

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

interface FormErrors {
  username?: string;
  password?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * LoginPage — /login
 *
 * Renders a username + password form. On successful POST /api/auth/login it
 * stores the JWT via AuthContext.login() and navigates to /credentials.
 *
 * Requirements 2.1–2.5:
 *  2.1  Login page is the application entry point.
 *  2.2  Valid credentials → session established → redirect to main app.
 *  2.3  Invalid credentials → generic error (no username/password hint).
 *  2.4  Backend issues JWT; stored in memory only.
 *  2.5  Expired token → redirect to /login (handled by apiClient interceptor).
 */
export default function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // ── Validation ──────────────────────────────────────────────────────────

  function validate(): FormErrors {
    const errors: FormErrors = {};
    if (!username.trim()) {
      errors.username = t("login.errorUsernameRequired");
    }
    if (!password) {
      errors.password = t("login.errorPasswordRequired");
    }
    return errors;
  }

  // ── Submit handler ──────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setApiError(null);

    const errors = validate();
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});

    setIsSubmitting(true);
    try {
      const { data } = await apiClient.post<LoginResponse>("/api/auth/login", {
        username: username.trim(),
        password,
      });

      login(data.access_token);
      navigate("/credentials", { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 401) {
          // Requirement 2.3: generic error — no hint about which field was wrong
          setApiError(t("login.genericError"));
        } else {
          setApiError(t("login.serverError"));
        }
      } else {
        setApiError(t("login.serverError"));
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
            {t("login.title")}
          </h1>

          <form onSubmit={handleSubmit} noValidate aria-label={t("login.title")}>
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
                htmlFor="login-username"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {t("login.usernameLabel")}
              </label>
              <input
                id="login-username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={t("login.usernamePlaceholder")}
                aria-required="true"
                aria-describedby={
                  fieldErrors.username ? "login-username-error" : undefined
                }
                className={[
                  "block w-full rounded-md border px-3 py-2",
                  "text-gray-900 placeholder-gray-400 text-sm",
                  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                  /* Touch-friendly height on mobile */
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
                  id="login-username-error"
                  role="alert"
                  className="mt-1 text-sm text-red-600"
                >
                  {fieldErrors.username}
                </p>
              )}
            </div>

            {/* Password field */}
            <div className="mb-6">
              <PasswordInput
                id="login-password"
                label={t("login.passwordLabel")}
                placeholder={t("login.passwordPlaceholder")}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-required="true"
                error={fieldErrors.password}
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
              {isSubmitting ? t("common.loading") : t("login.submitButton")}
            </button>
          </form>

          {/* Sign-up link */}
          <p className="mt-6 text-center text-sm text-gray-600">
            {t("login.noAccount")}{" "}
            <Link
              to="/signup"
              className="font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus:underline"
            >
              {t("login.signupLink")}
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
