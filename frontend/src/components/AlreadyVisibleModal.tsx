import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

export interface AlreadyVisibleModalProps {
  /**
   * Called when the user clicks "Continue".
   * The parent should:
   *  1. Hide the currently-visible password.
   *  2. Proceed to the Password_Confirmation_Prompt for the newly requested row.
   */
  onContinue: () => void;
  /** Called when the user clicks "Cancel" or presses Escape */
  onCancel: () => void;
}

/**
 * Warning modal shown when the user tries to reveal a credential password
 * while another password is already visible.
 *
 * - "Continue" → hides current password and proceeds to the new reveal flow
 * - "Cancel"   → closes the modal without changing anything
 *
 * - Traps focus within the modal
 * - Closes on Escape key
 * - auto-focuses the Cancel button (safer default — less disruptive action)
 */
export default function AlreadyVisibleModal({
  onContinue,
  onCancel,
}: AlreadyVisibleModalProps) {
  const { t } = useTranslation();
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  // Auto-focus Cancel button on mount
  useEffect(() => {
    cancelButtonRef.current?.focus();
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
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

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="avm-title"
      aria-describedby="avm-body"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      {/* Panel */}
      <div
        className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
        onKeyDown={handleKeyDownModal}
      >
        {/* Icon + Title */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-full bg-yellow-100">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 text-yellow-600"
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
          </div>

          <h2 id="avm-title" className="text-lg font-semibold text-gray-900">
            {t("alreadyVisibleModal.title")}
          </h2>
        </div>

        <p id="avm-body" className="text-sm text-gray-600 mb-6">
          {t("alreadyVisibleModal.body")}
        </p>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            ref={cancelButtonRef}
            onClick={onCancel}
            className={[
              "px-4 py-2 rounded-md text-sm font-medium",
              "border border-gray-300 text-gray-700",
              "hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500",
              "min-h-[44px] md:min-h-0",
            ].join(" ")}
          >
            {t("alreadyVisibleModal.cancelButton")}
          </button>

          <button
            type="button"
            onClick={onContinue}
            className={[
              "px-4 py-2 rounded-md text-sm font-medium",
              "bg-indigo-600 text-white",
              "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500",
              "min-h-[44px] md:min-h-0",
            ].join(" ")}
          >
            {t("alreadyVisibleModal.continueButton")}
          </button>
        </div>
      </div>
    </div>
  );
}
