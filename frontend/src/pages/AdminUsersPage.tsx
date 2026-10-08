import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";

// ── Types ────────────────────────────────────────────────────────────────────

interface Profile {
  profile_id: number;
  profile_name: string;
}

interface AdminUser {
  user_id: number;
  username: string;
  email: string;
  role: "User" | "Admin";
  profile: { profile_id: number; profile_name: string } | null;
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * AdminUsersPage — /admin/users
 *
 * Admin-only page that lists all users and lets the Admin reassign profiles.
 *
 * Requirements 3.2, 3.3, 3.5, 3.7:
 *  3.2  Admin-only profile assignment page.
 *  3.3  On assignment the backend updates permission set and audit columns.
 *  3.5  Admin has access to all application screens.
 *  3.7  Page lists all users with currently assigned Profile and allows reassignment.
 */
export default function AdminUsersPage() {
  const { t } = useTranslation();

  // ── Users list ──────────────────────────────────────────────────────────

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // ── Profiles (available options for the dropdown) ───────────────────────
  // Fetched from /api/admin/profiles if available; falls back to seed data.

  const [profiles, setProfiles] = useState<Profile[]>([]);

  // ── Per-row assignment state ─────────────────────────────────────────────
  // Maps user_id → { status: "idle" | "saving" | "success" | "error"; message? }

  type RowStatus = "idle" | "saving" | "success" | "error";
  const [rowStatus, setRowStatus] = useState<
    Record<number, { status: RowStatus; message?: string }>
  >({});

  // Track the currently-selected profile per row (controlled select)
  const [selectedProfiles, setSelectedProfiles] = useState<
    Record<number, number | "">
  >({});

  // ── Fetch users ──────────────────────────────────────────────────────────

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const response = await apiClient.get<AdminUser[]>("/api/admin/users");
      const data = response.data;
      setUsers(data);

      // Initialise the controlled select values from current assignments
      const initial: Record<number, number | ""> = {};
      for (const u of data) {
        initial[u.user_id] = u.profile?.profile_id ?? "";
      }
      setSelectedProfiles(initial);
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        // The apiClient response interceptor redirects to /login.
        return;
      }
      setFetchError(t("errors.generic"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  // ── Fetch profiles ───────────────────────────────────────────────────────

  const fetchProfiles = useCallback(async () => {
    try {
      const response = await apiClient.get<Profile[]>("/api/admin/profiles");
      setProfiles(response.data);
    } catch {
      // Fall back to seed data so the dropdown always has options
      setProfiles([
        { profile_id: 1, profile_name: "Basic" },
        { profile_id: 2, profile_name: "Full" },
      ]);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchProfiles();
  }, [fetchUsers, fetchProfiles]);

  // ── Handle dropdown change ───────────────────────────────────────────────

  async function handleProfileChange(userId: number, rawValue: string) {
    const profileId = rawValue === "" ? null : parseInt(rawValue, 10);

    // Update the controlled value immediately for responsive UI
    setSelectedProfiles((prev) => ({
      ...prev,
      [userId]: profileId ?? "",
    }));

    if (profileId === null) {
      // No-profile option selected — nothing to PUT
      return;
    }

    setRowStatus((prev) => ({
      ...prev,
      [userId]: { status: "saving" },
    }));

    try {
      await apiClient.put(`/api/admin/users/${userId}/profile`, {
        profile_id: profileId,
      });

      setRowStatus((prev) => ({
        ...prev,
        [userId]: { status: "success", message: t("admin.assignProfileSuccess") },
      }));

      // Auto-clear success message after 3 s
      setTimeout(() => {
        setRowStatus((prev) => ({
          ...prev,
          [userId]: { status: "idle" },
        }));
      }, 3000);
    } catch (err: unknown) {
      let message = t("admin.assignProfileError");
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        message = t("errors.forbidden");
      }
      setRowStatus((prev) => ({
        ...prev,
        [userId]: { status: "error", message },
      }));
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-5xl">

        {/* ── Page heading ── */}
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          {t("admin.usersPageTitle")}
        </h1>

        {/* ── Error banner ── */}
        {fetchError && (
          <div
            role="alert"
            aria-live="assertive"
            className="mb-5 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            {fetchError}
          </div>
        )}

        {/* ── Loading indicator ── */}
        {isLoading && (
          <p className="text-sm text-gray-500 mb-4" aria-live="polite">
            {t("common.loading")}
          </p>
        )}

        {/* ── Empty state ── */}
        {!isLoading && !fetchError && users.length === 0 && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("admin.noUsers")}
          </p>
        )}

        {/* ── Users table (Req 11.3 — horizontally scrollable on mobile) ── */}
        {!isLoading && users.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 bg-white">
              <thead className="bg-gray-50">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("admin.tableHeaderUser")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("admin.tableHeaderEmail")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("admin.tableHeaderRole")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("admin.tableHeaderProfile")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {t("admin.tableHeaderActions")}
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-gray-100">
                {users.map((user) => {
                  const rs = rowStatus[user.user_id] ?? { status: "idle" };
                  const isSaving = rs.status === "saving";

                  return (
                    <tr
                      key={user.user_id}
                      className="hover:bg-gray-50 transition-colors duration-100"
                    >
                      {/* Username */}
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 whitespace-nowrap">
                        {user.username}
                      </td>

                      {/* Email */}
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        {user.email}
                      </td>

                      {/* Role */}
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        <span
                          className={[
                            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                            user.role === "Admin"
                              ? "bg-indigo-100 text-indigo-800"
                              : "bg-gray-100 text-gray-700",
                          ].join(" ")}
                        >
                          {user.role}
                        </span>
                      </td>

                      {/* Current profile name */}
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        {user.profile?.profile_name ?? (
                          <span className="text-gray-400 italic">
                            {t("admin.noProfileAssigned")}
                          </span>
                        )}
                      </td>

                      {/* Actions — profile reassignment dropdown */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
                          {/* Label (sr-only on desktop to save space) */}
                          <label
                            htmlFor={`profile-select-${user.user_id}`}
                            className="sr-only"
                          >
                            {t("admin.assignProfileLabel")} {user.username}
                          </label>

                          {/* Profile dropdown */}
                          <select
                            id={`profile-select-${user.user_id}`}
                            value={selectedProfiles[user.user_id] ?? ""}
                            onChange={(e) =>
                              handleProfileChange(user.user_id, e.target.value)
                            }
                            disabled={isSaving}
                            className={[
                              "block rounded-md border border-gray-300 bg-white",
                              "px-2 py-1.5 text-sm text-gray-900",
                              "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                              "min-h-[44px] md:min-h-[36px]",
                              "disabled:opacity-60 disabled:cursor-not-allowed",
                            ].join(" ")}
                            aria-label={`${t("admin.assignProfileLabel")} ${user.username}`}
                          >
                            <option value="">
                              {t("admin.noProfileOption")}
                            </option>
                            {profiles.map((p) => (
                              <option key={p.profile_id} value={p.profile_id}>
                                {p.profile_name}
                              </option>
                            ))}
                          </select>

                          {/* Inline feedback */}
                          {isSaving && (
                            <span
                              className="text-xs text-gray-500"
                              aria-live="polite"
                            >
                              {t("common.loading")}
                            </span>
                          )}
                          {rs.status === "success" && (
                            <span
                              className="text-xs text-green-600"
                              role="status"
                              aria-live="polite"
                            >
                              {rs.message}
                            </span>
                          )}
                          {rs.status === "error" && (
                            <span
                              className="text-xs text-red-600"
                              role="alert"
                              aria-live="assertive"
                            >
                              {rs.message}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
