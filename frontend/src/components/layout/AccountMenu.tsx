import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ChevronDownIcon, LogOutIcon } from "../icons";

interface AccountMenuProps {
  username: string;
  role: string;
  onLogout: () => void;
}

/** Initials avatar until task 37.3 adds pictures. */
function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold uppercase text-white"
    >
      {name.slice(0, 2)}
    </span>
  );
}

/**
 * The account menu at the top right (Requirement 13.2): who is signed in,
 * their role and Sign out. Closes on Escape, on a click outside and after
 * choosing an option.
 */
export default function AccountMenu({ username, role, onLogout }: AccountMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

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
        <Avatar name={username} />
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-gray-700 sm:inline" data-testid="current-user">
          {username}
        </span>
        <ChevronDownIcon className="h-4 w-4 text-gray-500" />
      </button>

      {open && (
        <div
          id={menuId}
          className="absolute right-0 z-30 mt-2 w-60 rounded-md border border-gray-200 bg-white py-2 shadow-lg"
        >
          <div className="flex items-center gap-3 border-b border-gray-100 px-4 pb-3 pt-1">
            <Avatar name={username} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-900">{username}</p>
              <p className="text-xs text-gray-500">{t(`admin.roles.${role}`, { defaultValue: role })}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="mt-1 flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100 min-h-[44px]"
          >
            <LogOutIcon className="h-4 w-4" />
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  );
}
