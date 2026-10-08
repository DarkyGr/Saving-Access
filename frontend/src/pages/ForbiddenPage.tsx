import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

/**
 * ForbiddenPage — /forbidden
 *
 * Rendered when the backend returns 403 or the router guard detects the
 * authenticated user lacks permission for the requested screen.
 *
 * Requirements 2.5, 3.4, 3.6, 10.1:
 *  2.5  Expired / invalid token → redirect to /login (handled upstream).
 *  3.4  Insufficient profile permission → render this 403 page.
 *  3.6  Users without a profile assigned see this page for protected routes.
 *  10.1 A clear, localised 403 message with a link back to /credentials.
 */
export default function ForbiddenPage() {
  const { t } = useTranslation();

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md text-center">
        <div className="bg-white rounded-2xl shadow-md px-8 py-10">
          {/* Lock / shield icon */}
          <div className="flex justify-center mb-6" aria-hidden="true">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-16 w-16 text-red-400"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>

          <h1 className="text-2xl font-bold text-gray-900 mb-3">
            {t("forbidden.title")}
          </h1>

          <p className="text-sm text-gray-600 mb-8">
            {t("forbidden.message")}
          </p>

          <Link
            to="/credentials"
            className={[
              "inline-flex items-center justify-center rounded-md",
              "bg-indigo-600 text-white font-semibold text-sm",
              "px-6 py-3 min-h-[44px]",
              "hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2",
              "transition-colors duration-150",
            ].join(" ")}
          >
            {t("forbidden.goHomeButton")}
          </Link>
        </div>
      </div>
    </main>
  );
}
