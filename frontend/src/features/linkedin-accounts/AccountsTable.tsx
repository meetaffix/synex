import { MoreHorizontal } from "lucide-react";
import { Link } from "react-router-dom";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { AccountSummary } from "./management";
import type { SenderAccount } from "./schemas";
import type { RowActions } from "./AccountRow";

interface Props {
  accounts: SenderAccount[];
  summaries: Record<string, AccountSummary> | undefined;
  actionsFor: (account: SenderAccount) => RowActions;
  checkingId?: string;
  errors: Record<string, string>;
}

const percent = (value: number | null) => (value === null ? "no data" : `${value}%`);

/** The accounts as a table, the way OutFlo lists them: account, status, last 24 hours, performance, and a way in. Cards stay as the second view. */
export function AccountsTable({ accounts, summaries, actionsFor, checkingId, errors }: Props) {
  return (
    <div className="max-w-full overflow-x-auto rounded-lg border border-border bg-surface shadow-raised">
      <table aria-label="Connected accounts" className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead className="bg-surface-muted text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="px-4 py-3 font-medium">LinkedIn account</th>
            <th scope="col" className="px-4 py-3 font-medium">Status</th>
            <th scope="col" className="px-4 py-3 font-medium">Usage, last 24 h</th>
            <th scope="col" className="px-4 py-3 font-medium">Performance</th>
            <th scope="col" className="px-4 py-3 text-right font-medium"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((account) => {
            const actions = actionsFor(account);
            const summary = summaries?.[account.id];
            const disconnected = account.status === "disconnected";
            const canReconnect = account.status === "needs_reconnect" || disconnected;
            return (
              <tr key={account.id} className="border-t border-border align-middle">
                <td className="max-w-[190px] px-4 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <UserAvatar name={account.name} src={account.avatarUrl} className="size-10" />
                    <div className="min-w-0">
                      <Link to={`/linkedin-accounts/${account.id}`} className="block truncate font-semibold underline-offset-2 hover:underline" aria-label={`Manage ${account.name}: limits, privacy, health`}>{account.name}</Link>
                      <span className="block truncate text-xs text-muted-foreground">{account.headline ?? "No headline"}</span>
                      {errors[account.id] && <span role="alert" className="block text-xs text-danger">{errors[account.id]}</span>}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3"><StatusBadge kind="account" status={account.status} /></td>
                <td className="px-4 py-3">
                  {summary ? (
                    <div className="grid gap-1 whitespace-nowrap tabular-nums">
                      <span>Connections {summary.connections.sent} of {summary.connections.low} to {summary.connections.high}{summary.connections.queued ? ` (+${summary.connections.queued} waiting)` : ""}</span>
                      <span>Messages {summary.messages.sent} of {summary.messages.low} to {summary.messages.high}{summary.messages.queued ? ` (+${summary.messages.queued} waiting)` : ""}</span>
                      {summary.smart && <span className="w-fit rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-soft-foreground">Smart limits</span>}
                    </div>
                  ) : <span className="text-muted-foreground">{account.dailyActionLimit === 0 ? "Stopped" : `${account.dailyActionsUsed} of ${account.dailyActionLimit} actions`}</span>}
                </td>
                <td className="px-4 py-3">
                  {summary ? (
                    <div className="flex flex-wrap gap-2 whitespace-nowrap text-xs">
                      <span className="rounded-full bg-surface-muted px-2 py-0.5" title="Of the people invited, the share who accepted">Accepted {percent(summary.performance.acceptedPercent)}</span>
                      <span className="rounded-full bg-surface-muted px-2 py-0.5" title="Of the people Synex sent something to, the share who replied">Replied {percent(summary.performance.replyPercent)}</span>
                    </div>
                  ) : <span className="text-muted-foreground">No data</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    {canReconnect && <Button size="sm" onClick={actions.onReconnect}>Reconnect</Button>}
                    <Button size="sm" variant="secondary" onClick={actions.onCheck} loading={checkingId === account.id} disabled={disconnected}>Check now</Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="icon-sm" variant="ghost" aria-label={`More actions for ${account.name}`}><MoreHorizontal /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={actions.onEdit}>Edit account</DropdownMenuItem>
                        {!disconnected && <DropdownMenuItem onSelect={actions.onTogglePause}>{account.status === "paused" ? "Resume sending" : "Pause sending"}</DropdownMenuItem>}
                        <DropdownMenuItem onSelect={actions.onCopyLink}>Send a link so the owner reconnects it</DropdownMenuItem>
                        {!disconnected && (<><DropdownMenuSeparator /><DropdownMenuItem className="text-danger focus:text-danger" onSelect={actions.onDisconnect}>Disconnect</DropdownMenuItem></>)}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
