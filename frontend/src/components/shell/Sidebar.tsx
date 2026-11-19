import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { footerNav, primaryNav, type NavItem } from "./navigation";
import { COUNT_MEANING, useNavCounts } from "./useCounts";
import { UserMenu } from "./UserMenu";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface Props {
  collapsed?: boolean;
  /** Present on desktop only; the drawer has no collapse control. */
  onToggleCollapsed?: () => void;
  onOpenPalette?: () => void;
}

function Item({ item, collapsed, count }: { item: NavItem; collapsed: boolean; count: number }) {
  return (
    <NavLink
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "relative flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-lg:min-h-11",
          collapsed && "justify-center px-0",
          isActive
            ? "bg-primary-soft text-primary-soft-foreground shadow-[0_8px_18px_-10px_rgb(var(--primary)/0.55)] before:absolute before:-left-3 before:top-2 before:h-6 before:w-1 before:rounded-full before:bg-primary max-lg:before:-left-3"
            : "text-muted-foreground hover:bg-surface-muted hover:text-foreground",
        )
      }
    >
      <item.icon className="size-4 shrink-0" aria-hidden />
      <span className={cn("flex-1", collapsed && "sr-only")}>{item.label}</span>
      {count > 0 && (
        <span
          className={cn(
            "grid min-w-5 place-items-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground",
            collapsed && "absolute right-1 top-1 min-w-4 px-1",
          )}
        >
          {count}
          <span className="sr-only"> {COUNT_MEANING[item.to]}</span>
        </span>
      )}
    </NavLink>
  );
}

export function Sidebar({ collapsed = false, onToggleCollapsed, onOpenPalette }: Props) {
  const counts = useNavCounts();
  return (
    <div className="flex h-full flex-col gap-4 bg-gradient-to-b from-primary-soft/80 via-primary-soft/30 to-transparent px-3 py-4">
      <WorkspaceSwitcher collapsed={collapsed} />
      {onOpenPalette && (
        <button
          type="button"
          onClick={onOpenPalette}
          title={collapsed ? "Search (Ctrl K)" : undefined}
          className={cn(
            "flex min-h-10 items-center gap-3 rounded-md border border-border bg-surface px-3 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            collapsed && "justify-center px-0",
          )}
        >
          <Search className="size-4 shrink-0" aria-hidden />
          <span className={cn("flex-1 text-left", collapsed && "sr-only")}>Search</span>
          {!collapsed && <kbd className="rounded-sm border border-border px-1.5 text-xs">Ctrl K</kbd>}
        </button>
      )}
      <nav aria-label="Primary" className="grid gap-1">
        {primaryNav.map((item) => (
          <Item key={item.to} item={item} collapsed={collapsed} count={counts[item.to] ?? 0} />
        ))}
      </nav>
      <div className="mt-auto grid gap-1">
        <nav aria-label="Secondary" className="grid gap-1">
          {footerNav.map((item) => (
            <Item key={item.to} item={item} collapsed={collapsed} count={0} />
          ))}
        </nav>
        <div className="border-t border-border pt-2">
          <UserMenu compact={collapsed} onSidebar />
        </div>
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            className={cn(
              "flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors duration-150 hover:bg-surface-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              collapsed && "justify-center px-0",
            )}
          >
            {collapsed ? <PanelLeftOpen className="size-4" aria-hidden /> : <PanelLeftClose className="size-4" aria-hidden />}
            <span className={cn(collapsed && "sr-only")}>{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
          </button>
        )}
      </div>
    </div>
  );
}
