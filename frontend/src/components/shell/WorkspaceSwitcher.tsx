import { Check, ChevronsUpDown } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAuth } from "@/features/auth/AuthContext";
import { cn } from "@/lib/utils";

/** The workspace at the top of the sidebar. Synex has one workspace per account today, so the list has one entry. */
export function WorkspaceSwitcher({ collapsed }: { collapsed: boolean }) {
  const { user } = useAuth();
  const first = (user?.fullName ?? "").split(" ")[0];
  const name = first ? `${first}'s workspace` : "Your workspace";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={collapsed ? `${name}, switch workspace` : undefined}
        className={cn(
          "flex min-h-12 w-full items-center gap-3 rounded-md p-2 text-left transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          collapsed && "justify-center",
        )}
      >
        <LogoMark size={32} />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground">Synex</span>
              <span className="block truncate text-xs text-muted-foreground">{name}</span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
        <DropdownMenuItem className="justify-between" onSelect={(event) => event.preventDefault()}>
          {name}
          <Check className="size-4 text-primary-ink" aria-hidden />
        </DropdownMenuItem>
        <p className="px-3 pb-2 pt-1 text-xs text-muted-foreground">Each account has one workspace for now. Teams with several workspaces come later.</p>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
