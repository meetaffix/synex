import { NavLink, Outlet, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";

/** Settings keep one left menu, as OutFlo does: every settings page is one click from every other. */
const ITEMS = [
  { label: "Profile and assistant", to: "/settings", match: (p: string, s: string) => p === "/settings" },
  { label: "Integrations", to: "/settings/integrations", match: (p: string, s: string) => p === "/settings/integrations" && !/tab=(notifications|usage|support)/.test(s) },
  { label: "Notifications", to: "/settings/integrations?tab=notifications", match: (p: string, s: string) => p === "/settings/integrations" && s.includes("tab=notifications") },
  { label: "Usage", to: "/settings/integrations?tab=usage", match: (p: string, s: string) => p === "/settings/integrations" && s.includes("tab=usage") },
  { label: "Safety", to: "/settings/safety", match: (p: string) => p === "/settings/safety" },
  { label: "Support", to: "/settings/integrations?tab=support", match: (p: string, s: string) => p === "/settings/integrations" && s.includes("tab=support") },
];

export function SettingsLayout() {
  const { pathname, search } = useLocation();
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]">
      <nav aria-label="Settings sections">
        <ul className="flex flex-wrap gap-1 lg:grid">
          {ITEMS.map((item) => {
            const current = item.match(pathname, search);
            return (
              <li key={item.label}>
                <NavLink to={item.to} aria-current={current ? "page" : undefined}
                  className={cn("block rounded-md px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary", current ? "bg-primary-soft text-primary-soft-foreground" : "text-muted-foreground")}>
                  {item.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="min-w-0"><Outlet /></div>
    </div>
  );
}
