import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import apiClient from "../../api/apiClient";
import { describeDevice } from "../../lib/device";

interface TrustedDevice {
  device_id: number;
  user_agent: string | null;
  trusted_at: string;
  expires_at: string;
  last_used_at: string | null;
}

/**
 * Browsers that skip the two-step code (Requirement 21), shown in Settings →
 * Two-step verification, each one forgettable.
 */
export default function TrustedDevices() {
  const { t, i18n } = useTranslation();
  const [devices, setDevices] = useState<TrustedDevice[] | null>(null);
  const [error, setError] = useState(false);
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium" });

  const load = useCallback(() => {
    Promise.resolve(apiClient.get<TrustedDevice[]>("/api/profile/trusted-devices"))
      .then((res) => setDevices(res?.data ?? []))
      .catch(() => setError(true));
  }, []);

  useEffect(load, [load]);

  async function forget(path: string) {
    setError(false);
    try {
      await apiClient.delete(path);
      load();
    } catch {
      setError(true);
    }
  }

  function label(agent: string | null) {
    const { browser, os } = describeDevice(agent);
    return [browser, os].filter(Boolean).join(" · ") || t("trusted.unknown");
  }

  if (devices === null) return null;
  return (
    <div className="mt-4 border-t border-gray-100 pt-4">
      <h3 className="text-sm font-semibold text-gray-900">{t("trusted.title")}</h3>
      {devices.length === 0 ? (
        <p className="mt-1 text-sm text-gray-600">{t("trusted.none")}</p>
      ) : (
        <>
          <ul className="mt-2 divide-y divide-gray-100 rounded-md border border-gray-200">
            {devices.map((d) => (
              <li key={d.device_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span>
                  <span className="font-medium text-gray-900">{label(d.user_agent)}</span>
                  <span className="block text-xs text-gray-500">
                    {t("trusted.until", { date: date.format(new Date(d.expires_at)) })}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => void forget(`/api/profile/trusted-devices/${d.device_id}`)}
                  className="min-h-[36px] rounded-md border border-gray-300 px-3 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  {t("trusted.forget")}
                </button>
              </li>
            ))}
          </ul>
          {devices.length > 1 && (
            <button
              type="button"
              onClick={() => void forget("/api/profile/trusted-devices")}
              className="mt-2 text-sm font-medium text-red-600 hover:text-red-500"
            >
              {t("trusted.forgetAll")}
            </button>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {t("errors.generic")}
        </p>
      )}
    </div>
  );
}
