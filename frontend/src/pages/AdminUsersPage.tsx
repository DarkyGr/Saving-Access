import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";

type Role = "User" | "Admin";

interface AdminUser {
  user_id: number;
  username: string;
  email: string;
  role: Role;
  email_verified: boolean;
}

type RowStatus = { status: "idle" | "saving" | "success" | "error"; message?: string };

const ROLES: Role[] = ["User", "Admin"];

/**
 * AdminUsersPage — /admin/users (permission `users.manage`).
 *
 * Lists every account with its role and lets the Admin change another
 * account's role (Requirements 3.6, 3.7, task 37.1). The Admin's own row is
 * locked, so at least one Admin always remains; the backend enforces it too.
 */
export default function AdminUsersPage() {
  const { t } = useTranslation();
  const { user: me } = useAuth();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [rowStatus, setRowStatus] = useState<Record<number, RowStatus>>({});

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const response = await apiClient.get<AdminUser[]>("/api/admin/users");
      setUsers(response.data);
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

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  async function handleRoleChange(target: AdminUser, role: Role) {
    if (role === target.role) return;
    setRowStatus((prev) => ({ ...prev, [target.user_id]: { status: "saving" } }));
    try {
      await apiClient.put(`/api/admin/users/${target.user_id}/role`, { role });
      setUsers((prev) => prev.map((u) => (u.user_id === target.user_id ? { ...u, role } : u)));
      setRowStatus((prev) => ({
        ...prev,
        [target.user_id]: { status: "success", message: t("admin.changeRoleSuccess") },
      }));
      setTimeout(() => {
        setRowStatus((prev) => ({ ...prev, [target.user_id]: { status: "idle" } }));
      }, 3000);
    } catch (err: unknown) {
      const message =
        axios.isAxiosError(err) && err.response?.status === 403
          ? t("errors.forbidden")
          : t("admin.changeRoleError");
      setRowStatus((prev) => ({ ...prev, [target.user_id]: { status: "error", message } }));
    }
  }

  const th =
    "px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">{t("admin.usersPageTitle")}</h1>

        {fetchError && (
          <div
            role="alert"
            aria-live="assertive"
            className="mb-5 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            {fetchError}
          </div>
        )}

        {isLoading && (
          <p className="text-sm text-gray-500 mb-4" aria-live="polite">
            {t("common.loading")}
          </p>
        )}

        {!isLoading && !fetchError && users.length === 0 && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("admin.noUsers")}
          </p>
        )}

        {/* Req 11.3 — horizontally scrollable on mobile */}
        {!isLoading && users.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 bg-white">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className={th}>{t("admin.tableHeaderUser")}</th>
                  <th scope="col" className={th}>{t("admin.tableHeaderEmail")}</th>
                  <th scope="col" className={th}>{t("admin.tableHeaderRole")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((user) => {
                  const rs = rowStatus[user.user_id] ?? { status: "idle" };
                  const isMe = me?.user_id === user.user_id;
                  const selectId = `role-select-${user.user_id}`;
                  const lockedId = `role-locked-${user.user_id}`;
                  return (
                    <tr key={user.user_id} className="hover:bg-gray-50 transition-colors duration-100">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 whitespace-nowrap">
                        {user.username}
                        {isMe && <span className="ml-1 text-gray-500">{t("admin.youBadge")}</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">{user.email}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
                          <label htmlFor={selectId} className="sr-only">
                            {t("admin.changeRoleLabel", { username: user.username })}
                          </label>
                          <select
                            id={selectId}
                            value={user.role}
                            onChange={(e) => handleRoleChange(user, e.target.value as Role)}
                            disabled={isMe || rs.status === "saving"}
                            aria-describedby={isMe ? lockedId : undefined}
                            title={isMe ? t("admin.ownRoleLocked") : undefined}
                            className={[
                              "block rounded-md border border-gray-300 bg-white",
                              "px-2 py-1.5 text-sm text-gray-900",
                              "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                              "min-h-[44px] md:min-h-[36px]",
                              "disabled:opacity-60 disabled:cursor-not-allowed",
                            ].join(" ")}
                          >
                            {ROLES.map((role) => (
                              <option key={role} value={role}>
                                {t(`admin.roles.${role}`)}
                              </option>
                            ))}
                          </select>
                          {isMe && (
                            <span id={lockedId} className="text-xs text-gray-500">
                              {t("admin.ownRoleLocked")}
                            </span>
                          )}
                          {rs.status === "saving" && (
                            <span className="text-xs text-gray-500" aria-live="polite">
                              {t("common.loading")}
                            </span>
                          )}
                          {rs.status === "success" && (
                            <span className="text-xs text-green-600" role="status" aria-live="polite">
                              {rs.message}
                            </span>
                          )}
                          {rs.status === "error" && (
                            <span className="text-xs text-red-600" role="alert" aria-live="assertive">
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
