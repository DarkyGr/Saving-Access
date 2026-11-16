import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";

import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";
import { usePaged } from "../hooks/usePaged";
import { useListView } from "../hooks/useListView";
import { matchesQuery } from "../lib/text";
import { usePrivacy } from "../context/PreferencesContext";
import { FilterSelect, ListToolbar, Pagination, SearchBox, ViewToggle } from "../components/list/ListControls";
import ConfirmDialog from "../components/ConfirmDialog";
import DeactivateDialog from "../components/admin/DeactivateDialog";

type Role = "User" | "Admin";
type Status = "active" | "deactivated" | "locked" | "unverified";

export interface AdminUser {
  user_id: number;
  user_code: string;
  username: string;
  display_name: string | null;
  email: string;
  role: Role;
  email_verified: boolean;
  status: Status;
  deactivated_by: "admin" | "deadline" | null;
  deactivated_at: string | null;
  deactivation_reason: string | null;
  locked_at: string | null;
  two_factor: boolean;
  created: string | null;
}

type RowStatus = { status: "idle" | "saving" | "success" | "error"; message?: string };

const ROLES: Role[] = ["User", "Admin"];
const STATUSES: Status[] = ["active", "deactivated", "locked", "unverified"];

const STATUS_STYLE: Record<Status, string> = {
  active: "bg-green-50 text-green-700",
  unverified: "bg-amber-50 text-amber-700",
  deactivated: "bg-red-50 text-red-700",
  locked: "bg-amber-50 text-amber-800",
};

type Pending = { kind: "deactivate" | "reactivate" | "unlock" | "reset-2fa"; user: AdminUser } | null;

/**
 * AdminUsersPage — /admin/users (permission `users.manage`).
 *
 * Every account with its role; the Admin changes another account's role
 * (Requirements 3.6, 3.7, task 37.1). The Admin's own row is locked, so one
 * Admin always remains (the backend enforces it too). Task 37.2 adds search
 * by name or email, filters by role and verification, pagination and the
 * list / grid view saved in the account (Requirement 13.4). Task 37.4 adds
 * the user ID to the search, the status filter, and deactivating (with a
 * reason that is emailed) or reactivating another account (Requirement 15).
 */
export default function AdminUsersPage() {
  const { t, i18n } = useTranslation();
  const { user: me } = useAuth();
  const { mask } = usePrivacy();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [rowStatus, setRowStatus] = useState<Record<number, RowStatus>>({});

  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [pending, setPending] = useState<Pending>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useListView("users", "list");

  const filtered = useMemo(
    () =>
      users
        .filter(
          (u) =>
            matchesQuery(query, [u.username, u.email, u.user_code, u.display_name ?? ""]) &&
            (roleFilter === "" || u.role === roleFilter) &&
            (statusFilter === "" || u.status === statusFilter)
        )
        .sort((a, b) => a.username.localeCompare(b.username, i18n.language)),
    [users, query, roleFilter, statusFilter, i18n.language]
  );
  const paged = usePaged(filtered, view === "grid" ? 30 : 10, `${query}|${roleFilter}|${statusFilter}|${view}`);

  const fetchUsers = useCallback(async () => {
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

  const closeDialog = useCallback(() => {
    setPending(null);
    setActionError(null);
  }, []);

  async function runAction(reason?: string) {
    if (!pending) return;
    const { kind, user } = pending;
    setActionBusy(true);
    setActionError(null);
    try {
      const res = await apiClient.post<AdminUser>(
        `/api/admin/users/${user.user_id}/${kind}`,
        kind === "deactivate" ? { reason } : undefined
      );
      setUsers((prev) => prev.map((u) => (u.user_id === user.user_id ? { ...u, ...res.data } : u)));
      setNotice(t(`admin.${kind}.done`, { username: user.username }));
      setPending(null);
    } catch (err: unknown) {
      const code = axios.isAxiosError(err) ? err.response?.status : undefined;
      setActionError(code === 409 ? t(`admin.${kind}.conflict`) : t("errors.generic"));
    } finally {
      setActionBusy(false);
    }
  }

  function statusCell(user: AdminUser) {
    return (
      <div className="flex flex-col gap-1">
        <span className={`inline-flex w-fit rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[user.status]}`}>
          {t(`admin.status.${user.status}`)}
        </span>
        {user.deactivated_by === "admin" && user.deactivation_reason && (
          <span className="max-w-[16rem] whitespace-normal break-words text-xs text-gray-500">
            {t("admin.deactivatedReason", { reason: user.deactivation_reason })}
          </span>
        )}
        {user.deactivated_by === "deadline" && (
          <span className="max-w-[16rem] whitespace-normal text-xs text-gray-500">{t("admin.deactivatedDeadline")}</span>
        )}
      </div>
    );
  }

  function unlockButton(user: AdminUser) {
    if (me?.user_id === user.user_id || user.status !== "locked") return null;
    return (
      <button
        type="button"
        onClick={() => {
          setNotice(null);
          setPending({ kind: "unlock", user });
        }}
        aria-label={t("admin.unlock.label", { username: user.username })}
        className="min-h-[44px] md:min-h-[36px] rounded-md border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        {t("admin.unlock.button")}
      </button>
    );
  }

  function resetTwoFactorButton(user: AdminUser) {
    if (me?.user_id === user.user_id || !user.two_factor) return null;
    return (
      <button
        type="button"
        onClick={() => {
          setNotice(null);
          setPending({ kind: "reset-2fa", user });
        }}
        aria-label={t("admin.reset-2fa.label", { username: user.username })}
        className="min-h-[44px] md:min-h-[36px] rounded-md border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        {t("admin.reset-2fa.button")}
      </button>
    );
  }

  function actionButton(user: AdminUser) {
    if (me?.user_id === user.user_id) return null;
    const deactivated = user.status === "deactivated";
    const kind = deactivated ? "reactivate" : "deactivate";
    return (
      <button
        type="button"
        onClick={() => {
          setNotice(null);
          setPending({ kind, user });
        }}
        aria-label={t(`admin.${kind}.label`, { username: user.username })}
        className={[
          "min-h-[44px] md:min-h-[36px] rounded-md border px-3 text-sm font-medium",
          deactivated
            ? "border-gray-300 text-gray-700 hover:bg-gray-50"
            : "border-red-200 text-red-700 hover:bg-red-50",
        ].join(" ")}
      >
        {t(`admin.${kind}.button`)}
      </button>
    );
  }

  function userCell(user: AdminUser, strong = "font-medium") {
    return (
      <>
        <span className={`text-gray-900 ${strong}`}>
          {user.username}
          {me?.user_id === user.user_id && <span className="ml-1 font-normal text-gray-500">{t("admin.youBadge")}</span>}
        </span>
        <span className="block font-mono text-xs text-gray-500">{user.user_code}</span>
      </>
    );
  }

  function roleControl(user: AdminUser) {
    const rs = rowStatus[user.user_id] ?? { status: "idle" };
    const isMe = me?.user_id === user.user_id;
    const selectId = `role-select-${user.user_id}`;
    const lockedId = `role-locked-${user.user_id}`;
    return (
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
    );
  }

  const th = "px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const showList = !isLoading && !fetchError && paged.total > 0;

  return (
    <main className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-5xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">{t("admin.usersPageTitle")}</h1>

        <ListToolbar view={<ViewToggle view={view} onChange={setView} />}>
          <SearchBox id="user-search" value={query} onChange={setQuery} placeholder={t("admin.searchPlaceholder")} />
          <FilterSelect
            id="user-role-filter"
            label={t("admin.tableHeaderRole")}
            value={roleFilter}
            onChange={setRoleFilter}
            options={ROLES.map((r) => ({ value: r, label: t(`admin.roles.${r}`) }))}
          />
          <FilterSelect
            id="user-status-filter"
            label={t("admin.tableHeaderStatus")}
            value={statusFilter}
            onChange={setStatusFilter}
            options={STATUSES.map((s) => ({ value: s, label: t(`admin.status.${s}`) }))}
          />
        </ListToolbar>

        {notice && (
          <div role="status" className="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {notice}
          </div>
        )}

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
        {!isLoading && !fetchError && users.length > 0 && filtered.length === 0 && (
          <p className="text-sm text-gray-500" aria-live="polite">
            {t("admin.noResults")}
          </p>
        )}

        {/* Req 11.3 — horizontally scrollable on mobile */}
        {showList && view === "list" && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 bg-white">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className={th}>{t("admin.tableHeaderUser")}</th>
                  <th scope="col" className={th}>{t("admin.tableHeaderEmail")}</th>
                  <th scope="col" className={th}>{t("admin.tableHeaderStatus")}</th>
                  <th scope="col" className={th}>{t("admin.tableHeaderRole")}</th>
                  <th scope="col" className={th}>
                    <span className="sr-only">{t("admin.tableHeaderActions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {paged.pageItems.map((user) => (
                  <tr key={user.user_id} className="hover:bg-gray-50 transition-colors duration-100">
                    <td className="px-4 py-3 text-sm whitespace-nowrap">{userCell(user)}</td>
                    <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">{mask(user.email)}</td>
                    <td className="px-4 py-3 align-top">{statusCell(user)}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{roleControl(user)}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex justify-end gap-2">
                        {unlockButton(user)}
                        {resetTwoFactorButton(user)}
                        {actionButton(user)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showList && view === "grid" && (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {paged.pageItems.map((user) => (
              <li key={user.user_id} className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <p className="truncate text-base">{userCell(user, "font-semibold")}</p>
                <p className="truncate text-sm text-gray-600">{mask(user.email)}</p>
                <div>{statusCell(user)}</div>
                <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-2">
                  {roleControl(user)}
                  <div className="flex flex-wrap gap-2">
                    {unlockButton(user)}
                    {resetTwoFactorButton(user)}
                    {actionButton(user)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {showList && <Pagination paged={paged} id="users-pages" />}

        {pending?.kind === "deactivate" && (
          <DeactivateDialog
            username={pending.user.username}
            onConfirm={(reason) => void runAction(reason)}
            onCancel={closeDialog}
            busy={actionBusy}
            error={actionError}
          />
        )}
        {pending?.kind === "reset-2fa" && (
          <ConfirmDialog
            title={t("admin.reset-2fa.title", { username: pending.user.username })}
            message={actionError ?? t("admin.reset-2fa.message")}
            confirmLabel={t("admin.reset-2fa.confirm")}
            cancelLabel={t("common.cancel")}
            onConfirm={() => void runAction()}
            onCancel={closeDialog}
            busy={actionBusy}
          />
        )}
        {pending?.kind === "unlock" && (
          <ConfirmDialog
            title={t("admin.unlock.title", { username: pending.user.username })}
            message={actionError ?? t("admin.unlock.message")}
            confirmLabel={t("admin.unlock.confirm")}
            cancelLabel={t("common.cancel")}
            onConfirm={() => void runAction()}
            onCancel={closeDialog}
            busy={actionBusy}
          />
        )}
        {pending?.kind === "reactivate" && (
          <ConfirmDialog
            title={t("admin.reactivate.title", { username: pending.user.username })}
            message={actionError ?? t("admin.reactivate.message")}
            confirmLabel={t("admin.reactivate.confirm")}
            cancelLabel={t("common.cancel")}
            onConfirm={() => void runAction()}
            onCancel={closeDialog}
            busy={actionBusy}
          />
        )}
      </div>
    </main>
  );
}
