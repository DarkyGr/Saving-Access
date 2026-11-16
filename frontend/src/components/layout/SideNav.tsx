import { useState } from "react";
import { NavLink, useLocation } from "react-router";
import { useTranslation } from "react-i18next";

import { activeGroup, NAV_GROUPS, type NavGroup, type NavItem } from "../../config/navigation";
import { readLocal, writeLocal } from "../../lib/storage";
import { ChevronDownIcon } from "../icons";

const GROUPS_KEY = "savepass-nav-closed";

interface SideNavProps {
  items: NavItem[];
  /** Icons only (desktop rail); names go to tooltips and screen readers. */
  collapsed?: boolean;
  /** Called after a link is chosen (closes the phone drawer). */
  onNavigate?: () => void;
}

/**
 * The grouped menu (Requirement 13.1). Groups can be closed by their title;
 * the choice is remembered on this device and the group of the current
 * screen always stays open.
 */
export default function SideNav({ items, collapsed = false, onNavigate }: SideNavProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const [closed, setClosed] = useState<NavGroup[]>(() => readLocal<NavGroup[]>(GROUPS_KEY, []));
  const current = activeGroup(pathname, items);

  function toggle(group: NavGroup) {
    const next = closed.includes(group) ? closed.filter((g) => g !== group) : [...closed, group];
    setClosed(next);
    writeLocal(GROUPS_KEY, next);
  }

  const link = (item: NavItem) => {
    const Icon = item.icon;
    const label = t(item.labelKey);
    return (
      <li key={item.to}>
        <NavLink
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          title={collapsed ? label : undefined}
          aria-label={collapsed ? label : undefined}
          className={({ isActive }) =>
            [
              "flex items-center gap-3 rounded-md px-3 min-h-[44px] text-sm font-medium",
              collapsed ? "justify-center px-0" : "",
              isActive ? "bg-indigo-50 text-indigo-700" : "text-gray-700 hover:bg-gray-100",
            ].join(" ")
          }
        >
          <Icon className="h-5 w-5 shrink-0" />
          {!collapsed && <span className="truncate">{label}</span>}
        </NavLink>
      </li>
    );
  };

  return (
    <nav aria-label={t("nav.main")} className="flex flex-col gap-3 px-2 py-3">
      {NAV_GROUPS.map((group) => {
        const groupItems = items.filter((i) => i.group === group);
        if (groupItems.length === 0) return null;
        if (group === "home" || collapsed) {
          return (
            <ul key={group} className="flex flex-col gap-1">
              {groupItems.map(link)}
            </ul>
          );
        }
        const open = group === current || !closed.includes(group);
        const listId = `nav-group-${group}`;
        return (
          <div key={group}>
            <button
              type="button"
              onClick={() => toggle(group)}
              aria-expanded={open}
              aria-controls={listId}
              disabled={group === current}
              title={group === current ? t("nav.groupCurrent") : undefined}
              className="flex w-full items-center justify-between rounded px-3 py-1 text-xs font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-700 disabled:cursor-default disabled:hover:text-gray-500"
            >
              {t(`nav.groups.${group}`)}
              <ChevronDownIcon className={`h-4 w-4 transition-transform ${open ? "" : "-rotate-90"}`} />
            </button>
            {open && (
              <ul id={listId} className="mt-1 flex flex-col gap-1">
                {groupItems.map(link)}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}
