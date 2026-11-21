import { MoreHorizontal } from "lucide-react";
import { Link } from "react-router-dom";
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
import type { AccountSummary } from "./management";
import type { SenderAccount } from "./schemas";

const problemHints: Partial<Record<SenderAccount["status"], string>> = {
  connected: "Connected. Synex can use this account within its daily limits.",
  paused: "Paused by you. Nothing is sent until you resume it.",
  needs_reconnect: "LinkedIn signed this account out or asked for a check. Reconnect it to keep sending.",
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
  summary?: AccountSummary;
  /** Position in the list, so cards arrive one after another. */
  index?: number;
}

export function AccountRow({ account, actions, checking, error, summary, index = 0 }: Props) {
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
        {summary && (
          <div className="grid gap-2">
            <dl aria-label={`${account.name}: last 24 hours`} className="grid gap-1 text-sm">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">Connection requests, 24 h</dt>
                <dd className="tabular-nums">{summary.connections.used} of {summary.connections.low} to {summary.connections.high}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">Messages, 24 h</dt>
                <dd className="tabular-nums">{summary.messages.used} of {summary.messages.low} to {summary.messages.high}</dd>
              </div>
            </dl>
            <ul aria-label={`${account.name}: performance`} className="flex flex-wrap items-center gap-2 text-xs">
              {summary.health && <li className={`rounded-full px-2 py-0.5 font-semibold ${({ good: "bg-success-soft text-success", watch: "bg-warning-soft text-warning", risk: "bg-danger-soft text-danger" } as Record<string, string>)[summary.health.level] ?? ""}`} title="Safety score: how safe this account's activity looks to LinkedIn">Safety {summary.health.score}</li>}
              {summary.smart && <li className="rounded-full bg-primary-soft px-2 py-0.5 font-medium text-primary-soft-foreground">Smart limits</li>}
              <li className="rounded-full bg-surface-muted px-2 py-0.5" title="Of the people invited, the share who accepted">
                Accepted {summary.performance.acceptedPercent === null ? "no data" : `${summary.performance.acceptedPercent}%`}
              </li>
              <li className="rounded-full bg-surface-muted px-2 py-0.5" title="Of the people who accepted, the share who replied">
                Replied {summary.performance.replyPercent === null ? "no data" : `${summary.performance.replyPercent}%`}
              </li>
            </ul>
          </div>
        )}
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
        <Button asChild size="sm" variant="secondary">
          <Link to={`/linkedin-accounts/${account.id}`} aria-label={`Manage ${account.name}: limits, privacy, health`}>Manage</Link>
        </Button>
      </div>
    </Reveal>
  );
}
