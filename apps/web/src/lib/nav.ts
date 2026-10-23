import {
  ActivityIcon,
  BotIcon,
  BoxesIcon,
  CpuIcon,
  DatabaseZapIcon,
  FileSpreadsheetIcon,
  FlaskConicalIcon,
  KeyRoundIcon,
  LayoutDashboardIcon,
  ScrollTextIcon,
  SettingsIcon,
  ShieldCheckIcon,
  UsersIcon,
  UsersRoundIcon,
  WalletIcon,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** The page reads the global time range, so the top bar shows the picker. */
  usesRange?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: "Monitor",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboardIcon, usesRange: true },
      { href: "/requests", label: "Requests", icon: ActivityIcon },
      { href: "/agents", label: "Agents", icon: BotIcon, usesRange: true },
      { href: "/reports", label: "Reports", icon: FileSpreadsheetIcon },
    ],
  },
  {
    label: "Control",
    items: [
      { href: "/budgets", label: "Budgets", icon: WalletIcon },
      { href: "/policies", label: "Policies", icon: ShieldCheckIcon },
      { href: "/cache", label: "Cache", icon: DatabaseZapIcon },
    ],
  },
  {
    label: "Configure",
    items: [
      { href: "/projects", label: "Projects", icon: BoxesIcon, usesRange: true },
      { href: "/keys", label: "API keys", icon: KeyRoundIcon },
      { href: "/models", label: "Models", icon: CpuIcon },
      { href: "/playground", label: "Playground", icon: FlaskConicalIcon },
    ],
  },
  {
    label: "Organisation",
    items: [
      { href: "/teams", label: "Teams", icon: UsersRoundIcon },
      { href: "/users", label: "Users", icon: UsersIcon },
      { href: "/audit", label: "Audit log", icon: ScrollTextIcon },
      { href: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

/** The nav item a path belongs to: exact match for "/", prefix match otherwise. */
export function activeNavItem(pathname: string): NavItem | undefined {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return NAV_ITEMS.find((i) => i.href === "/");
  return NAV_ITEMS.filter((i) => i.href !== "/" && (path === i.href || path.startsWith(`${i.href}/`))).sort(
    (a, b) => b.href.length - a.href.length,
  )[0];
}

export function isActive(item: NavItem, pathname: string): boolean {
  return activeNavItem(pathname)?.href === item.href;
}

/** Whether the top bar shows the range picker for this path. */
export function pageUsesRange(pathname: string): boolean {
  return !!activeNavItem(pathname)?.usesRange;
}
