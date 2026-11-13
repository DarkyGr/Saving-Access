import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import apiClient from "../api/apiClient";
import { useAuth } from "../context/AuthContext";
import LanguageToggle from "./LanguageToggle";

/**
 * AppLayout — application shell rendered around every route.
 *
 * - Language toggle always visible in the header (Requirement 10.2).
 * - When authenticated: navigation filtered by the user's permissions
 *   (Requirements 3.4, 3.5) and a logout button.
 */

interface NavItem {
  to: string;
  screen: string;
  labelKey: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/credentials", screen: "credentials", labelKey: "nav.credentials" },
  { to: "/credentials/new", screen: "credentials.new", labelKey: "nav.saveCredential" },
  { to: "/admin/users", screen: "admin.users", labelKey: "nav.adminUsers" },
  { to: "/admin/profiles", screen: "admin.profiles", labelKey: "nav.adminProfiles" },
];

function usePermissions(token: string | null, role: string | undefined): string[] {
  const [permissions, setPermissions] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setPermissions([]);
      return;
    }
    if (role === "Admin") {
      setPermissions(["*"]);
      return;
    }
    apiClient
      .get<{ permissions: string[] }>("/api/profile/permissions")
      .then((res) => {
        if (!cancelled) setPermissions(res.data.permissions ?? []);
      })
      .catch(() => {
        if (!cancelled) setPermissions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token, role]);

  return permissions;
}

export default function AppLayout() {
  const { t } = useTranslation();
  const { token, user, logout } = useAuth();
  const navigate = useNavigate();
  const permissions = usePermissions(token, user?.role);

  const canSee = (screen: string) =>
    permissions.includes("*") || permissions.includes(screen);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    [
      "inline-flex items-center min-h-[44px] px-3 rounded-md text-sm font-medium",
      isActive ? "bg-indigo-50 text-indigo-700" : "text-gray-700 hover:bg-gray-100",
    ].join(" ");

  return (
    <>
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
          <span className="text-base font-bold text-gray-900">Save-Pass</span>

          {token && (
            <nav aria-label={t("nav.main")} className="flex flex-wrap gap-1">
              {NAV_ITEMS.filter((item) => canSee(item.screen)).map((item) => (
                <NavLink key={item.to} to={item.to} end className={linkClass}>
                  {t(item.labelKey)}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="hidden text-sm text-gray-600 sm:inline" data-testid="current-user">
                {user.username}
              </span>
            )}
            <LanguageToggle />
            {token && (
              <button
                type="button"
                onClick={handleLogout}
                className="min-h-[44px] rounded-md border border-gray-300 px-3 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                {t("nav.logout")}
              </button>
            )}
          </div>
        </div>
      </header>
      <Outlet />
    </>
  );
}
