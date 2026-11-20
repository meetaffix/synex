import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronsUpDown } from "lucide-react";
import { useThemeChoice } from "@/app/ThemeProvider";
import type { ThemeChoice } from "@/lib/theme";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UserAvatar } from "@/components/ui/avatar";
import { useAuth } from "@/features/auth/AuthContext";
import { cn } from "@/lib/utils";

interface Props {
  /** Avatar only, for the top bar and a collapsed sidebar. */
  compact?: boolean;
  /** Placed in the sidebar: full width, opening upwards. */
  onSidebar?: boolean;
}

const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "Match my device" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function UserMenu({ compact = false, onSidebar = false }: Props) {
  const { user, logout } = useAuth();
  const queries = useQueryClient();
  const navigate = useNavigate();
  const name = user?.fullName ?? "Account";
  const theme = useThemeChoice();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex items-center gap-3 rounded-md p-2 text-left text-sm transition-colors duration-150 hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          onSidebar && "w-full",
        )}
      >
        <span className="shrink-0">
          <UserAvatar name={name} className="size-8" />
        </span>
        {compact && <span className="sr-only">Account menu for {name}</span>}
        {!compact && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-foreground">{name}</span>
              <span className="block truncate text-xs capitalize text-muted-foreground">{user?.plan ?? "free"} plan</span>
            </span>
            <span className="sr-only">, account menu</span>
            <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={onSidebar ? "start" : "end"} side={onSidebar ? "top" : "bottom"} className="w-56">
        <DropdownMenuLabel className="truncate">{user?.email ?? name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/settings")}>Account settings</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/help")}>Help</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme.choice} onValueChange={(value) => theme.setChoice(value as ThemeChoice)}>
          {THEMES.map((option) => (
            <DropdownMenuRadioItem key={option.value} value={option.value}>
              {option.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            logout();
            queries.clear();
          }}
        >
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
