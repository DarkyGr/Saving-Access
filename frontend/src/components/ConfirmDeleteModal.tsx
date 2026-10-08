import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

export interface ConfirmDeleteModalProps {
  /** Website / credential name shown in the modal body */
  websiteName: string;
  /** Called when the user confirms deletion */
  onConfirm: () => void;
  /** Called when the user cancels or presses Escape */
  onCancel: () => void;
  /** Disable buttons while a delete is in progress */
  isLoading?: boolean;
}

/**
 * Generic confirmation modal for credential deletion.
 *
 * - Traps focus within the modal
 * - Closes on Escape key
 * - Cancel button receives auto-focus (destructive-action best practice)
 */
export default function ConfirmDeleteModal({
  websiteName,
  onConfirm,
  onCancel,
  isLoading = false,
}: ConfirmDeleteModalProps) {
  const { t } = useTranslation();
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  // Auto-focus cancel button on mount (safer default for destructive modal)
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
      role="dialog"
      aria-modal="true"
      aria-labelledby="cdm-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      {/* Panel */}
      <div
        className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
        onKeyDown={handleKeyDownModal}
      >
        {/* Icon */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-full bg-red-100">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 text-red-600"
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
          </div>

          <h2 id="cdm-title" className="text-lg font-semibold text-gray-900">
            {t("confirmDeleteModal.title")}
          </h2>
        </div>

        <p className="text-sm text-gray-600 mb-6">
          {t("confirmDeleteModal.body", { website: websiteName })}
        </p>

        <div className="flex justify-end gap-3">
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
            {t("confirmDeleteModal.cancelButton")}
          </button>

          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={[
              "px-4 py-2 rounded-md text-sm font-medium",
              "bg-red-600 text-white",
              "hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500",
              "min-h-[44px] md:min-h-0",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            ].join(" ")}
          >
            {isLoading ? t("common.loading") : t("confirmDeleteModal.confirmButton")}
          </button>
        </div>
      </div>
    </div>
  );
}
