import { useTranslation } from "react-i18next";

// ── Types ────────────────────────────────────────────────────────────────────

interface Profile {
  profile_id: number;
  profile_name: string;
  permitted_screens: string[];
}

// ── Seed data ────────────────────────────────────────────────────────────────
// There is no dedicated list-profiles API endpoint. The available profiles
// are defined by the database seed and surfaced here as static reference data.
// (Req 3.2, 3.3, 3.5, 3.7)

const PROFILES: Profile[] = [
  {
    profile_id: 1,
    profile_name: "Basic",
    permitted_screens: ["credentials"],
  },
  {
    profile_id: 2,
    profile_name: "Full",
    permitted_screens: [
      "credentials",
      "credentials.new",
      "credentials.edit",
      "credentials.delete",
    ],
  },
];

// ── Screen badge ─────────────────────────────────────────────────────────────

interface ScreenBadgeProps {
  screenKey: string;
}

function ScreenBadge({ screenKey }: ScreenBadgeProps) {
  const { t } = useTranslation();

  // Map a screen key to its display label via i18n. Falls back to the raw key
  // so new keys never silently disappear.
  const label = t(`adminProfiles.screenNames.${screenKey}`, {
    defaultValue: screenKey,
  });

  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-2.5 py-0.5",
        "text-xs font-medium",
        "bg-indigo-100 text-indigo-800",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

// ── Profile card ─────────────────────────────────────────────────────────────

interface ProfileCardProps {
  profile: Profile;
}

function ProfileCard({ profile }: ProfileCardProps) {
  const { t } = useTranslation();

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      {/* Profile name */}
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-semibold text-gray-900">
          {profile.profile_name}
        </h2>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
          {t("adminProfiles.profileId", { id: profile.profile_id })}
        </span>
      </div>

      {/* Permitted screens label */}
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
        {t("adminProfiles.permittedScreensLabel")}
      </p>

      {/* Badges */}
      <div className="flex flex-wrap gap-2">
        {profile.permitted_screens.map((screen) => (
          <ScreenBadge key={screen} screenKey={screen} />
        ))}
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

/**
 * AdminProfilesPage — /admin/profiles
 *
 * Admin-only reference page that lists all available profiles and the screens
 * each one grants to a User-role account.
 *
 * Requirements:
 *  3.2  System provides an Admin-only profile assignment page.
 *  3.3  Admin assigns / modifies Profiles; audit columns updated.
 *  3.5  Admin role has full access to all screens.
 *  3.7  Admin page lists all users with their assigned Profile.
 *
 * Note: Actual profile *assignment* lives on AdminUsersPage (task 23.1).
 * This page is the reference view of which profiles exist and what they permit.
 * Route protection (Admin-only) is enforced by <ProtectedRoute screen="admin.profiles" />.
 */
export default function AdminProfilesPage() {
  const { t } = useTranslation();

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-3xl">

        {/* ── Page header ── */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">
            {t("admin.profilesPageTitle")}
          </h1>

          {/* Descriptive note (Req 3.4 — profiles control User screen access) */}
          <p className="mt-2 text-sm text-gray-600">
            {t("adminProfiles.description")}
          </p>
        </div>

        {/* ── Role model note ── */}
        <div className="mb-6 rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {t("adminProfiles.adminNote")}
        </div>

        {/* ── Profile cards ── */}
        {PROFILES.length === 0 ? (
          <p className="text-sm text-gray-500">{t("admin.noProfiles")}</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {PROFILES.map((profile) => (
              <ProfileCard key={profile.profile_id} profile={profile} />
            ))}
          </div>
        )}

        {/* ── All available screens reference ── */}
        <div className="mt-8">
          <h2 className="mb-3 text-base font-semibold text-gray-900">
            {t("adminProfiles.allScreensTitle")}
          </h2>
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("adminProfiles.screenKeyHeader")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("adminProfiles.screenDescriptionHeader")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {(
                  [
                    "credentials",
                    "credentials.new",
                    "credentials.edit",
                    "credentials.delete",
                    "admin.users",
                    "admin.profiles",
                  ] as const
                ).map((key) => (
                  <tr key={key} className="hover:bg-gray-50 transition-colors duration-100">
                    <td className="px-4 py-2.5 text-sm font-mono text-gray-700 whitespace-nowrap">
                      {key}
                    </td>
                    <td className="px-4 py-2.5 text-sm text-gray-600">
                      {t(`adminProfiles.screenNames.${key}`, {
                        defaultValue: key,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </main>
  );
}
