import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient, { setAuthToken } from "../api/apiClient";
import { useFocusFirstError } from "../hooks/useFocusFirstError";
import { START_PATHS, type StartPage } from "../context/PreferencesContext";
import { useAuth } from "../context/AuthContext";
import PasswordInput from "../components/PasswordInput";
import HCaptcha, { type HCaptchaHandle } from "../components/HCaptcha";
import { getAuthConfig, type AuthConfig } from "../api/authConfig";
import CodeStep from "../components/auth/CodeStep";
import TwoFactorSetup, { type SetupStart } from "../components/auth/TwoFactorSetup";
import RecoveryCodes from "../components/auth/RecoveryCodes";

// ── Types ────────────────────────────────────────────────────────────────────

interface LoginResponse {
  access_token: string | null;
  token_type: string;
  expires_in: number | null;
  email_verification_required?: boolean;
  deactivation_deadline?: string | null;
  // Task 37.5: after a right password, the second step to take.
  mfa?: "code" | "setup" | null;
  mfa_token?: string | null;
  recovery_codes?: string[] | null;
}

type SecondStep = { kind: "code" | "setup"; token: string } | null;

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
 *  2.6  hCaptcha challenge before submitting, when configured (task 33).
 *  2.7  Unverified email → verification modal after login (AppLayout).
 *  2.9  Deactivated account → explicit message (403).
 */
/** Where to go after signing in: the start page chosen in Settings (task 37.3). */
async function startPath(): Promise<string> {
  try {
    const res = await apiClient.get<{ start_page?: StartPage }>("/api/profile/preferences");
    return START_PATHS[res?.data?.start_page ?? "home"] ?? "/";
  } catch {
    return "/";
  }
}

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const justRegistered = Boolean(
    (location.state as { registered?: boolean } | null)?.registered
  );
  // Task 37.5: why the previous session ended, when it ended by itself.
  const sessionEnded = (location.state as { sessionEnded?: "idle" | "max" } | null)?.sessionEnded;

  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const captchaRef = useRef<HCaptchaHandle>(null);

  useEffect(() => {
    let cancelled = false;
    void getAuthConfig().then((c) => {
      if (!cancelled) setConfig(c);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const siteKey = config?.captcha_site_key ?? null;

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const formRef = useRef<HTMLFormElement>(null);
  const focusFirstError = useFocusFirstError(formRef);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [step, setStep] = useState<SecondStep>(null);
  // After setting 2FA up: the codes to save, and the session they open.
  const [pendingCodes, setPendingCodes] = useState<{ codes: string[]; data: LoginResponse } | null>(null);

  /** The session is open: go to the start page. */
  async function finish(data: LoginResponse) {
    if (!data.access_token) return;
    // Ask for the start page first: login() swaps the layout, which
    // remounts this page, so navigating after another await would be lost.
    setAuthToken(data.access_token);
    const target = await startPath();
    login(
      data.access_token,
      data.email_verification_required ? { deadline: data.deactivation_deadline ?? null } : null
    );
    navigate(target, { replace: true });
  }

  function startOver() {
    setStep(null);
    setPendingCodes(null);
    setPassword("");
  }

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
      focusFirstError();
      return;
    }
    setFieldErrors({});

    if (siteKey && !captchaToken) {
      setApiError(t("login.captchaRequired"));
      return;
    }

    setIsSubmitting(true);
    try {
      const { data } = await apiClient.post<LoginResponse>("/api/auth/login", {
        username: username.trim(),
        password,
        ...(siteKey ? { captcha_token: captchaToken } : {}),
      });

      if (data.mfa && data.mfa_token) {
        setStep({ kind: data.mfa, token: data.mfa_token });
        return;
      }
      await finish(data);
    } catch (err: unknown) {
      // hCaptcha tokens are single-use: always ask for a new challenge.
      captchaRef.current?.reset();
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        if (status === 401) {
          // Requirement 2.3: generic error — no hint about which field was wrong
          setApiError(t("login.genericError"));
        } else if (status === 403) {
          setApiError(t("login.accountDeactivated"));
        } else if (status === 423) {
          setApiError(t("login.accountLocked"));
        } else if (status === 400) {
          setApiError(t("login.captchaFailed"));
        } else if (status === 429) {
          setApiError(t("login.tooManyAttempts"));
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

  // Task 37.5: second step after a right password.
  if (step) {
    const title = pendingCodes
      ? t("twoFactor.codesTitle")
      : step.kind === "setup"
        ? t("twoFactor.setupTitle")
        : t("twoFactor.codeTitle");
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-md px-8 py-10">
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-6">{title}</h1>
          {pendingCodes ? (
            <RecoveryCodes
              codes={pendingCodes.codes}
              doneLabel={t("twoFactor.continue")}
              onDone={() => void finish(pendingCodes.data)}
            />
          ) : step.kind === "setup" ? (
            <>
              <p className="mb-4 text-sm text-gray-700">{t("twoFactor.setupRequired")}</p>
              <TwoFactorSetup
                start={async () =>
                  (await apiClient.post<SetupStart>("/api/auth/2fa/setup", { mfa_token: step.token })).data
                }
                confirm={async (code) => {
                  const { data } = await apiClient.post<LoginResponse>("/api/auth/2fa/confirm", {
                    mfa_token: step.token,
                    code,
                  });
                  setPendingCodes({ codes: data.recovery_codes ?? [], data });
                }}
              />
            </>
          ) : (
            <CodeStep
              onCancel={startOver}
              verify={async (code) => {
                const { data } = await apiClient.post<LoginResponse>("/api/auth/login/verify", {
                  mfa_token: step.token,
                  code,
                });
                await finish(data);
              }}
            />
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-md px-8 py-10">
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-8">
            {t("login.title")}
          </h1>

          <form ref={formRef} onSubmit={handleSubmit} noValidate aria-label={t("login.title")}>
            {justRegistered && !apiError && (
              <div
                role="status"
                className="mb-5 rounded-md bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800"
              >
                {config?.email_verification
                  ? t("login.registeredVerify")
                  : t("login.registered")}
              </div>
            )}

            {sessionEnded && !apiError && (
              <div role="status" className="mb-5 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {sessionEnded === "idle" ? t("session.endedIdle") : t("session.endedMax")}
              </div>
            )}

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
                aria-invalid={!!fieldErrors.username}
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

            {siteKey && (
              <div className="mb-6">
                <HCaptcha
                  ref={captchaRef}
                  siteKey={siteKey}
                  language={i18n.language}
                  onToken={setCaptchaToken}
                  onLoadError={() => setApiError(t("login.captchaUnavailable"))}
                />
              </div>
            )}

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

          <p className="mt-4 text-center text-sm">
            <Link to="/forgot-password" className="font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus:underline">
              {t("login.forgotLink")}
            </Link>
          </p>

          {/* Sign-up link */}
          <p className="mt-4 text-center text-sm text-gray-600">
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
