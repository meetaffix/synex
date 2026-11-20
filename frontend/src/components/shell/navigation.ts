import {
  CircleHelp,
  FileText,
  Inbox,
  LayoutDashboard,
  Shapes,
  Linkedin,
  Send,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

/** The primary sidebar, in order. Posting is a secondary tool and lives under Others. */
export const primaryNav: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
  { label: "Inbox", to: "/inbox", icon: Inbox },
  { label: "Campaigns", to: "/campaigns", icon: Send },
  { label: "Sender accounts", to: "/linkedin-accounts", icon: Linkedin },
  { label: "Leads", to: "/leads", icon: Users },
  { label: "Templates", to: "/templates", icon: FileText },
  { label: "Others", to: "/others", icon: Shapes },
];

export const footerNav: NavItem[] = [
  { label: "Settings", to: "/settings", icon: Settings },
  { label: "Help", to: "/help", icon: CircleHelp },
];

export interface Crumb {
  label: string;
  to?: string;
}

const publishingPages: Record<string, string> = {
  studio: "Studio",
  calendar: "Calendar",
  queue: "Queue",
  activity: "Activity",
  analytics: "Analytics",
  connections: "Connections",
};

/** Breadcrumb trail for a pathname. The last crumb is the current page and has no link. */
export function breadcrumbsFor(pathname: string): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "others") {
    const trail: Crumb[] = [{ label: "Others", to: "/others" }];
    if (parts[1] === "publishing") {
      trail.push({ label: "Content publishing", to: "/others/publishing" });
      if (parts[2]) trail.push({ label: publishingPages[parts[2]] ?? parts[2] });
    }
    const last = trail[trail.length - 1];
    return trail.length === 1 ? [{ label: last.label }] : [...trail.slice(0, -1), { label: last.label }];
  }
  const item = [...primaryNav, ...footerNav].find((entry) => parts[0] === entry.to.slice(1));
  return [{ label: item?.label ?? "Synex" }];
}
