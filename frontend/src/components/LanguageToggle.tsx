import { useTranslation } from "react-i18next";

type Lang = "en" | "es";

const LANGUAGES: { code: Lang; labelKey: string }[] = [
  { code: "en", labelKey: "language.en" },
  { code: "es", labelKey: "language.es" },
];

/**
 * Header language-toggle button group.
 *
 * Calls `i18n.changeLanguage()` on click and also writes the chosen
 * language to `sessionStorage` under the key `"i18nextLng"` so the
 * preference persists for the duration of the browser session.
 *
 * The active language button is visually distinguished.
 */
export default function LanguageToggle() {
  const { t, i18n } = useTranslation();

  const currentLang = i18n.language?.slice(0, 2) as Lang;

  const handleChange = (lang: Lang) => {
    i18n.changeLanguage(lang);
    sessionStorage.setItem("i18nextLng", lang);
  };

  return (
    <div
      role="group"
      aria-label={t("language.toggle")}
      className="inline-flex rounded-md border border-gray-300 overflow-hidden"
    >
      {LANGUAGES.map(({ code, labelKey }, idx) => {
        const isActive = currentLang === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => handleChange(code)}
            aria-pressed={isActive}
            aria-label={t(labelKey)}
            className={[
              "px-3 py-1 text-sm font-medium",
              /* Divider between buttons */
              idx > 0 ? "border-l border-gray-300" : "",
              /* ≥ 44px touch target on mobile */
              "min-h-[44px] md:min-h-[32px]",
              "focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500",
              isActive
                ? "bg-indigo-600 text-white"
                : "bg-white text-gray-700 hover:bg-gray-50",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {code.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}
