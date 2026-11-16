import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";

import { usePreferences } from "../../context/PreferencesContext";
import Avatar from "../profile/Avatar";
import { ChevronDownIcon, LogOutIcon, SettingsIcon } from "../icons";

interface AccountMenuProps {
  username: string;
  role: string;
  onLogout: () => void;
}

/**
 * The account menu at the top right (Requirements 13.2, 14.1): avatar, the
 * name shown in the app, the user ID and role, Settings and Log out. Closes
 * on Escape, on a click outside and after choosing an option.
 */
export default function AccountMenu({ username, role, onLogout }: AccountMenuProps) {
  const { t } = useTranslation();
  const { me, prefs, avatarUrl } = usePreferences();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const shown = me?.display_name || username;

  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item = "flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 min-h-[44px]";

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={t("account.menuLabel", { username })}
        className="flex min-h-[44px] items-center gap-2 rounded-md px-2 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <Avatar name={shown} preset={prefs.avatar_preset} imageUrl={avatarUrl} />
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-gray-700 sm:inline" data-testid="current-user">
          {username}
        </span>
        <ChevronDownIcon className="h-4 w-4 text-gray-500" />
      </button>

      {open && (
        <div id={menuId} className="absolute right-0 z-30 mt-2 w-64 rounded-md border border-gray-200 bg-white py-2 shadow-lg">
          <div className="flex items-center gap-3 border-b border-gray-100 px-4 pb-3 pt-1">
            <Avatar name={shown} preset={prefs.avatar_preset} imageUrl={avatarUrl} size="md" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-900">{shown}</p>
              <p className="text-xs text-gray-500">
                {t(`admin.roles.${role}`, { defaultValue: role })}
                {me?.user_code ? ` · ${me.user_code}` : ""}
              </p>
            </div>
          </div>
          <Link to="/settings" onClick={() => setOpen(false)} className={`mt-1 ${item}`}>
            <SettingsIcon className="h-4 w-4" />
            {t("nav.settings")}
          </Link>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className={item}
          >
            <LogOutIcon className="h-4 w-4" />
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  );
}
