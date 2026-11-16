import type { ComponentType } from "react";

import { HistoryIcon, HomeIcon, KeyIcon, PlusIcon, SlidersIcon, UsersIcon } from "../components/icons";

/**
 * The side menu, declared in one place (Requirement 13.1, task 37.2).
 *
 * Every entry names the permission it needs (task 37.1); entries the user
 * lacks are hidden and a group with no visible entry is not shown. "home" is
 * shown on its own; the others are collapsible groups. Settings belong to the
 * user and live in the account menu, not here.
 */
export const NAV_GROUPS = ["home", "vault", "admin", "help"] as const;
export type NavGroup = (typeof NAV_GROUPS)[number];

export interface NavItem {
  /** Message key under `nav`. */
  labelKey: string;
  to: string;
  icon: ComponentType<{ className?: string }>;
  group: NavGroup;
  permission: string;
  /** Match only this exact path (otherwise sub-paths keep it active). */
  end?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { labelKey: "nav.home", to: "/", icon: HomeIcon, group: "home", permission: "credentials.view", end: true },
  { labelKey: "nav.credentials", to: "/credentials", icon: KeyIcon, group: "vault", permission: "credentials.view", end: true },
  { labelKey: "nav.saveCredential", to: "/credentials/new", icon: PlusIcon, group: "vault", permission: "credentials.create", end: true },
  { labelKey: "nav.adminUsers", to: "/admin/users", icon: UsersIcon, group: "admin", permission: "users.manage", end: true },
  { labelKey: "nav.adminAudit", to: "/admin/audit", icon: HistoryIcon, group: "admin", permission: "audit.view", end: true },
  { labelKey: "nav.adminSettings", to: "/admin/settings", icon: SlidersIcon, group: "admin", permission: "settings.manage", end: true },
];

export function visibleItems(permissions: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => permissions.includes(item.permission));
}

/** The group whose entry matches *pathname* best (longest prefix). */
export function activeGroup(pathname: string, items: readonly NavItem[]): NavGroup | null {
  let best: NavItem | null = null;
  for (const item of items) {
    const matches = item.to === "/" ? pathname === "/" : pathname === item.to || pathname.startsWith(`${item.to}/`);
    if (matches && (!best || item.to.length > best.to.length)) best = item;
  }
  return best?.group ?? null;
}
