import { useState, forwardRef } from "react";
import { useTranslation } from "react-i18next";

export interface PasswordInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Optional label rendered above the input */
  label?: string;
  /** Error message rendered below the input */
  error?: string;
}

/**
 * Masked password input with an Eye_Toggle button.
 * Toggles between type="password" and type="text".
 * Touch target for the toggle is ≥ 44×44 px on mobile (< 768 px).
 */
const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ label, error, id, className = "", ...rest }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);

    const inputId = id ?? "password-input";

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            {label}
          </label>
        )}

        <div className="relative flex items-center">
          <input
            {...rest}
            id={inputId}
            ref={ref}
            type={visible ? "text" : "password"}
            className={[
              "block w-full rounded-md border border-gray-300 px-3 py-2 pr-12",
              "text-gray-900 placeholder-gray-400",
              "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
              "text-sm",
              error ? "border-red-500 focus:ring-red-500 focus:border-red-500" : "",
              className,
            ]
              .filter(Boolean)
              .join(" ")}
            aria-describedby={error ? `${inputId}-error` : undefined}
          />

          {/* Eye_Toggle button — min 44×44 px touch target on mobile */}
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={
              visible
                ? t("credentials.hideButton")
                : t("credentials.revealButton")
            }
            aria-pressed={visible}
            className={[
              "absolute right-0 flex items-center justify-center",
              "h-full px-3",
              /* ≥ 44px touch target on screens < 768 px */
              "min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0",
              "text-gray-500 hover:text-gray-700 focus:outline-none",
              "focus:ring-2 focus:ring-inset focus:ring-indigo-500 rounded-r-md",
            ].join(" ")}
          >
            {visible ? (
              /* Eye-off icon */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            ) : (
              /* Eye icon */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5"
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
            )}
          </button>
        </div>

        {error && (
          <p id={`${inputId}-error`} role="alert" className="mt-1 text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    );
  }
);

PasswordInput.displayName = "PasswordInput";

export default PasswordInput;
