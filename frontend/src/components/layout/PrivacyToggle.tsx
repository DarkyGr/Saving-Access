import { useTranslation } from "react-i18next";

import { usePrivacy } from "../../context/PreferencesContext";
import { EyeIcon, EyeOffIcon } from "../icons";

/** The eye in the top bar (Requirement 14.3): hide usernames and emails. */
export default function PrivacyToggle() {
  const { t } = useTranslation();
  const { hidden, toggle } = usePrivacy();
  const label = hidden ? t("privacy.show") : t("privacy.hide");
  return (
    <button
      type="button"
      onClick={() => void toggle()}
      aria-pressed={hidden}
      aria-label={label}
      title={label}
      className="flex h-11 w-11 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100"
    >
      {hidden ? <EyeOffIcon /> : <EyeIcon />}
    </button>
  );
}
