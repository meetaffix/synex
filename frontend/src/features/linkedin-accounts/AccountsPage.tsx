import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState as SharedEmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { AccountRow, type RowActions } from "./AccountRow";
import { AccountsTable } from "./AccountsTable";
import { ConnectDialog } from "./ConnectDialog";
import { EditAccountDialog } from "./EditAccountDialog";
import { ReconnectLinkDialog, type LinkState } from "./ReconnectLinkDialog";
import { complianceNote, requestFailureMessage } from "./copy";
import { pendingConnectAttempt, useAccountActions, useSenderAccounts } from "./hooks";
import { useOverview } from "./management";
import type { SenderAccount } from "./schemas";

const PAGE = 9;

export function SenderAccountsPage() {
  const accounts = useSenderAccounts();
  const actions = useAccountActions();
  const overview = useOverview();
  const usage = useMemo(() => Object.values(overview.data?.accounts ?? {}).reduce((sum, a) => ({ connections: sum.connections + a.connections.used, messages: sum.messages + a.messages.used }), { connections: 0, messages: 0 }), [overview.data]);
  const [params, setParams] = useSearchParams();
  // "Connect LinkedIn account" links here with ?connect=1: open the form, then drop the flag so a reload does not reopen it.
  const [connecting, setConnecting] = useState<{ reconnecting?: string } | null>(params.get("connect") === "1" || pendingConnectAttempt() ? {} : null);
  useEffect(() => {
    if (params.get("connect") === "1") {
      params.delete("connect");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);
  const [editing, setEditing] = useState<SenderAccount | null>(null);
  const [disconnecting, setDisconnecting] = useState<SenderAccount | null>(null);
  const [link, setLink] = useState<{ account: SenderAccount; state: LinkState } | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  // OutFlo lists accounts in a table; Synex keeps its cards as the second view. The choice is remembered in the address.
  const view = params.get("view") === "cards" ? "cards" : "table";
  const setView = (next: "table" | "cards") => { const q = new URLSearchParams(params); if (next === "table") q.delete("view"); else q.set("view", next); setParams(q, { replace: true }); };
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(0);
  const matches = useMemo(
    () =>
      (accounts.data ?? []).filter((a) => {
        const group = statusFilter === "active" ? a.status === "connected" : statusFilter === "attention" ? ["needs_reconnect", "restricted", "disconnected"].includes(a.status) : statusFilter === "all" || a.status === statusFilter;
        return group && a.name.toLowerCase().includes(query.trim().toLowerCase());
      }),
    [accounts.data, query, statusFilter],
  );
  const shown = matches.slice(page * PAGE, page * PAGE + PAGE);

  const setRowError = (id: string, message?: string) =>
    setRowErrors((current) => {
      const { [id]: _removed, ...rest } = current;
      return message ? { ...rest, [id]: message } : rest;
    });

  const createLink = (account: SenderAccount) => {
    setLink({ account, state: { kind: "loading" } });
    actions.reconnectLink.mutate(account.id, {
      onSuccess: (created) => setLink({ account, state: { kind: "ready", link: created } }),
      onError: (error) => setLink({ account, state: { kind: "error", message: requestFailureMessage(error) } }),
    });
  };

  const rowActions = (account: SenderAccount): RowActions => ({
    onCheck: () =>
      actions.check.mutate(account.id, {
        onSuccess: (checked) => {
          setRowError(account.id);
          toast.success(`${checked.name} checked: ${checked.status.replaceAll("_", " ")}.`);
        },
        onError: (error) => setRowError(account.id, `The last check failed. ${requestFailureMessage(error)}`),
      }),
    onTogglePause: () =>
      actions.update.mutate(
        { id: account.id, changes: { paused: account.status !== "paused" } },
        {
          onSuccess: () => setRowError(account.id),
          onError: (error) => setRowError(account.id, `Could not change sending. ${requestFailureMessage(error)}`),
        },
      ),
    onEdit: () => {
      actions.update.reset();
      setEditing(account);
    },
    onReconnect: () => setConnecting({ reconnecting: account.name }),
    onCopyLink: () => createLink(account),
    onDisconnect: () => setDisconnecting(account),
  });

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeader
        title="Sender accounts"
        description="The LinkedIn profiles Synex sends connection requests and messages from."
        // One primary action per view: while the list is empty, the empty state carries it.
        actions={accounts.data?.length === 0 ? undefined : <Button onClick={() => setConnecting({})}>Connect LinkedIn account</Button>}
      />

      {!!accounts.data?.length && overview.data && (
        <section aria-label="Workspace overview" className="flex flex-wrap items-center gap-x-8 gap-y-2 rounded-lg border border-border bg-surface p-4 text-sm" data-testid="seats">
          <p><span className="text-muted-foreground">Plan</span> <span className="font-medium">{overview.data.plan}</span> <span className="text-subtle">(placeholder: billing is not built yet)</span></p>
          <p><span className="text-muted-foreground">Seats used</span> <span className="font-medium">{overview.data.seatsUsed} of {overview.data.seatsIncluded}</span></p>
          <p><span className="text-muted-foreground">Seats available</span> <span className="font-medium">{overview.data.seatsAvailable}</span></p>
          <p data-testid="usage-meter"><span className="text-muted-foreground">Last 24 hours</span> <span className="font-medium">{usage.connections} connection requests, {usage.messages} messages</span></p>
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <Link className="font-medium underline underline-offset-2" to="/settings/integrations?tab=usage">View usage</Link>
            <Button size="sm" variant="outline" disabled aria-describedby="plan-soon">Manage plan</Button>
            <span id="plan-soon" className="text-xs text-muted-foreground">Coming soon: Synex does not sell plans yet.</span>
          </span>
        </section>
      )}
      {accounts.isLoading && <LoadingList />}
      {accounts.isError && !accounts.data && (
        <Problem message={requestFailureMessage(accounts.error)} onRetry={() => void accounts.refetch()} />
      )}
      {accounts.isError && accounts.data && (
        <Problem
          message={`Showing the last list Synex loaded. It could not refresh: ${requestFailureMessage(accounts.error)}`}
          onRetry={() => void accounts.refetch()}
        />
      )}
      {accounts.data?.length === 0 && <EmptyState onConnect={() => setConnecting({})} />}
      {!!accounts.data?.length && (
        <div className="flex flex-wrap items-center gap-3">
          <Input aria-label="Search accounts" placeholder="Search accounts" className="max-w-xs" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} />
          <NativeSelect aria-label="Filter by status" className="w-auto" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="attention">Needs attention</option>
            <option value="connected">Connected</option>
            <option value="paused">Paused</option>
            <option value="needs_reconnect">Needs reconnect</option>
            <option value="restricted">Restricted</option>
            <option value="disconnected">Disconnected</option>
          </NativeSelect>
          <div role="group" aria-label="List view" className="ml-auto flex gap-1">
            <Button size="sm" variant={view === "table" ? "default" : "outline"} aria-pressed={view === "table"} onClick={() => setView("table")}>Table</Button>
            <Button size="sm" variant={view === "cards" ? "default" : "outline"} aria-pressed={view === "cards"} onClick={() => setView("cards")}>Cards</Button>
          </div>
        </div>
      )}
      {!!accounts.data?.length && shown.length === 0 && <p role="status" className="text-sm text-muted-foreground">No accounts match.</p>}
      {!!shown.length && view === "table" && (
        <div className="hidden min-w-0 max-w-full md:block"><AccountsTable accounts={shown} summaries={overview.data?.accounts} actionsFor={rowActions} checkingId={actions.check.isPending ? (actions.check.variables as string) : undefined} errors={rowErrors} /></div>
      )}
      {!!shown.length && (
        <ul aria-label="Connected accounts" className={`${view === "table" ? "md:hidden " : ""}grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[repeat(2,minmax(0,1fr))] xl:grid-cols-[repeat(3,minmax(0,1fr))]`}>
          {shown.map((account, index) => (
            <AccountRow
              key={account.id}
              index={index}
              account={account}
              actions={rowActions(account)}
              checking={actions.check.isPending && actions.check.variables === account.id}
              error={rowErrors[account.id]}
              summary={overview.data?.accounts[account.id]}
            />
          ))}
        </ul>
      )}
      {matches.length > PAGE && (
        <nav aria-label="Account pages" className="flex items-center gap-3 text-sm">
          <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
          <span>{page * PAGE + 1} to {Math.min((page + 1) * PAGE, matches.length)} of {matches.length}</span>
          <Button size="sm" variant="outline" disabled={(page + 1) * PAGE >= matches.length} onClick={() => setPage(page + 1)}>Next</Button>
        </nav>
      )}
      {!!accounts.data?.length && <p className="text-xs text-muted-foreground">{complianceNote}</p>}

      {connecting && (
        <ConnectDialog open onOpenChange={(open) => !open && setConnecting(null)} reconnecting={connecting.reconnecting} />
      )}
      {editing && (
        <EditAccountDialog
          account={editing}
          saving={actions.update.isPending}
          error={actions.update.isError ? requestFailureMessage(actions.update.error) : undefined}
          onClose={() => setEditing(null)}
          onSave={(changes) =>
            actions.update.mutate({ id: editing.id, changes }, { onSuccess: () => setEditing(null) })
          }
        />
      )}
      {link && (
        <ReconnectLinkDialog accountName={link.account.name} state={link.state} onRetry={() => createLink(link.account)} onClose={() => setLink(null)} />
      )}
      <ConfirmDialog
        open={!!disconnecting}
        onOpenChange={(open) => !open && setDisconnecting(null)}
        title={`Disconnect ${disconnecting?.name ?? "this account"}?`}
        description="Synex removes the saved LinkedIn session and any reconnect link, so this account stops sending. It keeps the account's name, its campaigns, conversations and activity history. You can reconnect it later."
        confirmLabel="Disconnect"
        destructive
        loading={actions.disconnect.isPending}
        onConfirm={() =>
          disconnecting &&
          actions.disconnect.mutate(disconnecting.id, {
            onSuccess: () => {
              toast.success(`${disconnecting.name} disconnected.`);
              setDisconnecting(null);
            },
            onError: (error) => toast.error(requestFailureMessage(error)),
          })
        }
      />
    </div>
  );
}

function EmptyState({ onConnect }: { onConnect: () => void }) {
  return (
    <SharedEmptyState
      illustration="accounts"
      title="No sender accounts yet"
      description="A sender account is a LinkedIn profile that Synex sends connection requests and messages from. You sign in once, Synex keeps the session, and each account has its own daily limit and optional proxy."
      action={<Button onClick={onConnect}>Connect LinkedIn account</Button>}
    />
  );
}

function LoadingList() {
  return (
    <div role="status" aria-label="Loading accounts" className="grid gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="grid flex-1 gap-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function Problem({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg bg-danger-soft p-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-danger">{message}</p>
      <Button size="sm" variant="outline" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
