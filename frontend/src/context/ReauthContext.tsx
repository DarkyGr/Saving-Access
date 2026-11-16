import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import PasswordConfirmModal from "../components/PasswordConfirmModal";

/** The API asks for the password again (Requirement 16.5, task 37.5). */
export const REAUTH_REQUIRED = "Re-authentication required.";

/** Thrown by `withReauth` when the person closes the password dialog. */
export class ReauthCancelled extends Error {
  constructor() {
    super("Re-authentication cancelled.");
    this.name = "ReauthCancelled";
  }
}

function needsReauth(err: unknown): boolean {
  return (
    axios.isAxiosError(err) &&
    err.response?.status === 403 &&
    (err.response.data as { detail?: unknown } | undefined)?.detail === REAUTH_REQUIRED
  );
}

type Ask = () => Promise<void>;

const ReauthContext = createContext<Ask>(() => Promise.reject(new ReauthCancelled()));

/**
 * Asks for the account password when an administration action needs a
 * recent check, confirms it (`POST /api/profile/session/reauth`) and lets the
 * action run again.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const pending = useRef<{ resolve: () => void; reject: (e: Error) => void } | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const ask = useCallback<Ask>(
    () =>
      new Promise<void>((resolve, reject) => {
        pending.current = { resolve, reject };
        setError(undefined);
        setOpen(true);
      }),
    []
  );

  async function confirm(password: string) {
    setBusy(true);
    setError(undefined);
    try {
      await apiClient.post("/api/profile/session/reauth", { account_password: password });
      setOpen(false);
      pending.current?.resolve();
      pending.current = null;
    } catch (err: unknown) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(
        status === 401
          ? t("passwordConfirmModal.errorWrongPassword")
          : status === 429
            ? t("settings.tooManyAttempts")
            : t("errors.generic")
      );
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    setOpen(false);
    pending.current?.reject(new ReauthCancelled());
    pending.current = null;
  }

  return (
    <ReauthContext.Provider value={ask}>
      {children}
      {open && <PasswordConfirmModal onConfirm={(pw) => void confirm(pw)} onCancel={cancel} error={error} isLoading={busy} />}
    </ReauthContext.Provider>
  );
}

/** Run an administration request; ask for the password once if the API wants it. */
export function useReauth() {
  const ask = useContext(ReauthContext);
  return useCallback(
    async <T,>(request: () => Promise<T>): Promise<T> => {
      try {
        return await request();
      } catch (err: unknown) {
        if (!needsReauth(err)) throw err;
        await ask();
        return await request();
      }
    },
    [ask]
  );
}
