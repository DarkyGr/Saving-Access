import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";

import { useAuth } from "../context/AuthContext";
import { visibleItems } from "../config/navigation";
import { usePermissions } from "../hooks/usePermissions";
import { usePreferences } from "../context/PreferencesContext";
import { readLocal, writeLocal } from "../lib/storage";
import LanguageToggle from "./LanguageToggle";
import VerifyEmailModal from "./VerifyEmailModal";
import SideNav from "./layout/SideNav";
import AccountMenu from "./layout/AccountMenu";
import PrivacyToggle from "./layout/PrivacyToggle";
import { ChevronsLeftIcon, ChevronsRightIcon, CloseIcon, MenuIcon } from "./icons";

const COLLAPSED_KEY = "savepass-sidebar-collapsed";

/**
 * AppLayout — application shell rendered around every route.
 *
 * - Language toggle always visible (Requirement 10.2).
 * - Signed in (Requirement 13.1–13.2, task 37.2): side menu grouped by
 *   section and filtered by the user's permissions (task 37.1). On wide
 *   screens it collapses to icons (remembered on this device); below 768 px
 *   it opens as a drawer that closes after choosing a screen. The account
 *   menu at the top right shows who is signed in and signs out.
 */
export default function AppLayout() {
  const { t } = useTranslation();
  const { token, user, logout, verificationNotice, dismissVerificationNotice } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const permissions = usePermissions(token, user?.role);
  const items = visibleItems(permissions);

  const [collapsed, setCollapsed] = useState<boolean>(() => readLocal(COLLAPSED_KEY, false));
  const [drawerOpen, setDrawerOpen] = useState(false);

  // A new screen closes the phone drawer.
  useEffect(() => setDrawerOpen(false), [pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  function toggleCollapsed() {
    setCollapsed((v) => {
      writeLocal(COLLAPSED_KEY, !v);
      return !v;
    });
  }

  async function handleLogout() {
    // False when someone signed in again while the session was being
    // revoked: then they stay where that sign-in took them.
    if (await logout()) navigate("/login", { replace: true });
  }

  if (!token || !user) {
    return (
      <>
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-2">
            <span className="text-base font-bold text-gray-900">Save-Pass</span>
            <div className="ml-auto">
              <LanguageToggle />
            </div>
          </div>
        </header>
        <Outlet />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 md:flex">
      {/* Desktop side menu */}
      <aside
        className={[
          "hidden md:flex md:flex-col md:shrink-0 border-r border-gray-200 bg-white",
          "md:sticky md:top-0 md:h-screen md:overflow-y-auto transition-[width] duration-150",
          collapsed ? "md:w-16" : "md:w-60",
        ].join(" ")}
      >
        <div className={`flex h-14 items-center border-b border-gray-200 ${collapsed ? "justify-center" : "justify-between px-4"}`}>
          {!collapsed && <span className="text-base font-bold text-gray-900">Save-Pass</span>}
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
            title={collapsed ? t("nav.expand") : t("nav.collapse")}
            className="flex h-10 w-10 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-700"
          >
            {collapsed ? <ChevronsRightIcon /> : <ChevronsLeftIcon />}
          </button>
        </div>
        <SideNav items={items} collapsed={collapsed} />
      </aside>

      {/* Phone drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label={t("nav.menu")}>
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col overflow-y-auto bg-white shadow-xl">
            <div className="flex h-14 items-center justify-between border-b border-gray-200 px-4">
              <span className="text-base font-bold text-gray-900">Save-Pass</span>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label={t("nav.closeMenu")}
                className="flex h-11 w-11 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100"
              >
                <CloseIcon />
              </button>
            </div>
            <SideNav items={items} onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-gray-200 bg-white px-2 sm:px-4">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label={t("nav.openMenu")}
            aria-expanded={drawerOpen}
            className="flex h-11 w-11 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100 md:hidden"
          >
            <MenuIcon />
          </button>
          <span className="text-base font-bold text-gray-900 md:hidden">Save-Pass</span>
          <div className="ml-auto flex items-center gap-2">
            <PrivacyToggle />
            <LanguageToggle />
            <AccountMenu username={user.username} role={user.role} onLogout={handleLogout} />
          </div>
        </header>
        <RecoveryCodesWarning />
        <Outlet />
      </div>

      {verificationNotice && (
        <VerifyEmailModal deadline={verificationNotice.deadline} onClose={dismissVerificationNotice} />
      )}
    </div>
  );
}

/** Requirement 16.1: warn when 3 or fewer recovery codes remain. */
function RecoveryCodesWarning() {
  const { t } = useTranslation();
  const { me } = usePreferences();
  const status = me?.two_factor;
  if (!status?.enabled || status.recovery_codes_left > 3) return null;
  return (
    <div role="status" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
      {t("twoFactor.lowCodes", { count: status.recovery_codes_left })}{" "}
      <Link to="/settings" className="font-medium underline">
        {t("twoFactor.lowCodesLink")}
      </Link>
    </div>
  );
}
