import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

export interface Tab {
  label: string;
  to: string;
  /** Match the address exactly (for a section's first tab). */
  end?: boolean;
  /** Decide "current" yourself, for tabs that differ only by query string. */
  current?: boolean;
}

/** Text tabs with a 2px primary underline on the current one. Each tab is a link, so it can be opened and shared. */
export function TabNav({ label, tabs }: { label: string; tabs: Tab[] }) {
  return (
    <nav aria-label={label} className="flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          aria-current={tab.current === undefined ? undefined : tab.current ? "page" : undefined}
          className={({ isActive }) => {
            const current = tab.current ?? isActive;
            return cn(
              "-mb-px flex min-h-10 items-center whitespace-nowrap border-b-2 px-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring max-sm:min-h-11",
              current ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            );
          }}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
