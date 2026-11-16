import { MoreHorizontal } from "lucide-react";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Reveal } from "@/lib/motion";
import { formatDate, formatRelative } from "@/utils/format";
import type { SenderAccount } from "./schemas";

const problemHints: Partial<Record<SenderAccount["status"], string>> = {
  needs_reconnect: "LinkedIn signed this account out. Reconnect it to keep sending.",
  restricted: "LinkedIn has restricted this account. Resolve it on LinkedIn, then check again.",
  disconnected: "This account is disconnected. Reconnect it to send again.",
};

export interface RowActions {
  onCheck: () => void;
  onTogglePause: () => void;
  onEdit: () => void;
  onReconnect: () => void;
  onCopyLink: () => void;
  onDisconnect: () => void;
}

interface Props {
  account: SenderAccount;
  actions: RowActions;
  checking: boolean;
  error?: string;
  /** Position in the list, so cards arrive one after another. */
  index?: number;
}

export function AccountRow({ account, actions, checking, error, index = 0 }: Props) {
  const percent = account.dailyActionLimit > 0 ? Math.min(100, (account.dailyActionsUsed / account.dailyActionLimit) * 100) : 0;
  const hint = account.pausedReason ?? problemHints[account.status];
  const canReconnect = account.status === "needs_reconnect" || account.status === "disconnected";
  const disconnected = account.status === "disconnected";
  const stopped = account.dailyActionLimit === 0;
  const nearLimit = !stopped && percent >= 80;

  return (
    <Reveal
      as="li"
      index={index}
      className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-4 rounded-lg border border-border bg-surface p-4 shadow-raised transition-transform duration-200 hover:-translate-y-0.5 sm:p-6"
    >
      <div className="flex items-start gap-3">
        <UserAvatar name={account.name} src={account.avatarUrl} className="size-12" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold">{account.name}</h2>
          <p className="truncate text-sm text-muted-foreground">{account.headline ?? "No headline"}</p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label={`More actions for ${account.name}`}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {!disconnected && (
              <DropdownMenuItem onSelect={actions.onTogglePause}>{account.status === "paused" ? "Resume sending" : "Pause sending"}</DropdownMenuItem>
            )}
            <DropdownMenuItem onSelect={actions.onCopyLink}>Send a link so the owner reconnects it</DropdownMenuItem>
            {!disconnected && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-danger focus:text-danger" onSelect={actions.onDisconnect}>
                  Disconnect
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="grid gap-3 text-sm">
        <dl className="grid gap-3">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Health</dt>
            <dd>
              <StatusBadge kind="account" status={account.status} />
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Actions today</dt>
            <dd className={nearLimit || stopped ? "font-medium text-warning" : undefined}>
              {stopped ? "Stopped" : `${account.dailyActionsUsed} today, up to ${account.dailyActionLimit} a day`}
              {nearLimit && <span className="sr-only"> (close to the daily limit)</span>}
            </dd>
          </div>
        </dl>
        <Progress
          value={percent}
          aria-label={`${account.name} actions today`}
          aria-valuetext={stopped ? "Stopped" : `${account.dailyActionsUsed} today, up to ${account.dailyActionLimit} a day`}
          className="h-2"
          indicatorClassName={nearLimit ? "bg-warning" : undefined}
        />
        <dl className="grid gap-3">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Proxy</dt>
            <dd>{account.proxyConfigured ? "Set" : "None"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Last check</dt>
            <dd title={account.lastCheckedAt ? formatDate(account.lastCheckedAt, "PPpp") : undefined}>
              {account.lastCheckedAt ? formatRelative(account.lastCheckedAt) : "Not checked yet"}
            </dd>
          </div>
        </dl>
      </div>

      {hint && <p className="rounded-md bg-surface-muted p-3 text-sm text-muted-foreground">{hint}</p>}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {canReconnect && (
          <Button size="sm" onClick={actions.onReconnect}>
            Reconnect
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={actions.onCheck} loading={checking} disabled={disconnected}>
          Check now
        </Button>
        <Button size="sm" variant="secondary" onClick={actions.onEdit}>
          Edit
        </Button>
      </div>
    </Reveal>
  );
}
