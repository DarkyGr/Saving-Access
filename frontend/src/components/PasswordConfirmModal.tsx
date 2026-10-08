import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import PasswordInput from "./PasswordInput";

export interface PasswordConfirmModalProps {
  /** Called with the entered password when the user confirms */
  onConfirm: (password: string) => void;
  /** Called when the user cancels or presses Escape */
  onCancel: () => void;
  /** Optional error message to display (e.g., wrong password) */
  error?: string;
  /** Whether the confirm button is in a loading/submitting state */
  isLoading?: boolean;
}

/**
 * Modal dialog that prompts the user to re-enter their account password
 * before a sensitive operation is executed.
 *
 * - Traps focus within the modal
 * - Closes on Escape key
 * - auto-focuses the password input on mount
 */
export default function PasswordConfirmModal({
  onConfirm,
  onCancel,
  error,
  isLoading = false,
}: PasswordConfirmModalProps) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const passwordInputRef = useRef<HTMLInputElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  // Auto-focus the password field when modal opens
  useEffect(() => {
    passwordInputRef.current?.focus();
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  // Trap focus within modal
  const handleKeyDownModal = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab") return;

    const focusable = e.currentTarget.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password.trim()) {
      onConfirm(password);
    }
  };

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pcm-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      {/* Panel */}
      <div
        className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
        onKeyDown={handleKeyDownModal}
      >
        {/* Title */}
        <h2
          id="pcm-title"
          className="text-lg font-semibold text-gray-900 mb-1"
        >
          {t("passwordConfirmModal.title")}
        </h2>

        <p className="text-sm text-gray-500 mb-4">
          {t("passwordConfirmModal.description")}
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <PasswordInput
            ref={passwordInputRef}
            id="pcm-password"
            label={t("passwordConfirmModal.passwordLabel")}
            placeholder={t("passwordConfirmModal.passwordPlaceholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={error}
            autoComplete="current-password"
            disabled={isLoading}
          />

          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              ref={cancelButtonRef}
              onClick={onCancel}
              disabled={isLoading}
              className={[
                "px-4 py-2 rounded-md text-sm font-medium",
                "border border-gray-300 text-gray-700",
                "hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                "min-h-[44px] md:min-h-0",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              ].join(" ")}
            >
              {t("passwordConfirmModal.cancelButton")}
            </button>

            <button
              type="submit"
              disabled={isLoading || !password.trim()}
              className={[
                "px-4 py-2 rounded-md text-sm font-medium",
                "bg-indigo-600 text-white",
                "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                "min-h-[44px] md:min-h-0",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              ].join(" ")}
            >
              {isLoading ? t("common.loading") : t("passwordConfirmModal.confirmButton")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
