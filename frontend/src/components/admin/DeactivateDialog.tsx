import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

const MIN = 3;
const MAX = 500;

/**
 * Deactivate an account with a reason (Requirement 15.2, task 37.4). The
 * reason is required and is emailed to the person. Escape or the backdrop
 * cancel; the reason box gets the focus.
 */
export default function DeactivateDialog({
  username,
  onConfirm,
  onCancel,
  busy = false,
  error = null,
}: {
  username: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string | null;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const hintId = useId();
  const errorId = useId();
  const fieldId = useId();
  const field = useRef<HTMLTextAreaElement>(null);
  const [reason, setReason] = useState("");
  const [tooShort, setTooShort] = useState(false);

  useEffect(() => {
    field.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const clean = reason.split(/\s+/).filter(Boolean).join(" ");
    if (clean.length < MIN) {
      setTooShort(true);
      field.current?.focus();
      return;
    }
    onConfirm(clean);
  }

  const message = tooShort ? t("admin.deactivate.reasonRequired") : error;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} aria-hidden="true" />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onSubmit={submit}
        noValidate
        className="relative w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 id={titleId} className="text-lg font-semibold text-gray-900">
          {t("admin.deactivate.title", { username })}
        </h2>
        <p id={hintId} className="mt-2 text-sm text-gray-600">
          {t("admin.deactivate.message")}
        </p>
        <label htmlFor={fieldId} className="mt-4 block text-sm font-medium text-gray-700">
          {t("admin.deactivate.reason")}
        </label>
        <textarea
          id={fieldId}
          ref={field}
          value={reason}
          maxLength={MAX}
          rows={3}
          onChange={(e) => {
            setReason(e.target.value);
            setTooShort(false);
          }}
          aria-invalid={tooShort}
          aria-describedby={message ? `${hintId} ${errorId}` : hintId}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-[invalid=true]:border-red-500"
        />
        <p className="mt-1 text-right text-xs text-gray-500">
          {reason.length}/{MAX}
        </p>
        {message && (
          <p id={errorId} role="alert" className="mt-1 text-sm text-red-600">
            {message}
          </p>
        )}
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="min-h-[44px] rounded-md bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
          >
            {t("admin.deactivate.confirm")}
          </button>
        </div>
      </form>
    </div>
  );
}
