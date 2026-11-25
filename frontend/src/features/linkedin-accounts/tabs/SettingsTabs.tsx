import { useEffect, useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ReconnectLinkDialog, type LinkState } from "../ReconnectLinkDialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { requestFailureMessage } from "../copy";
import { useAccountActions } from "../hooks";
import { useManagementActions, type AccountDetails, type SenderPolicy } from "../management";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatRelative } from "@/utils/format";
import type { SenderAccount, SyncMode } from "../schemas";
import { SyncModeFields } from "../SyncModeFields";

export function PrivacyTab({ account, details }: { account: SenderAccount; details: AccountDetails }) {
  const id = useId();
  const actions = useAccountActions();
  const { savePolicy } = useManagementActions(account.id);
  const [days, setDays] = useState(details.policy.inboxHistoryDays);
  useEffect(() => setDays(details.policy.inboxHistoryDays), [details.policy.inboxHistoryDays]);
  const allowed = details.canChangePrivacy;
  const [link, setLink] = useState<LinkState | null>(null);
  const share = () => {
    setLink({ kind: "loading" });
    actions.reconnectLink.mutate(account.id, {
      onSuccess: (created) => setLink({ kind: "ready", link: created }),
      onError: (error) => setLink({ kind: "error", message: requestFailureMessage(error) }),
    });
  };
  const changeSync = (mode: SyncMode) =>
    actions.update.mutate(
      { id: account.id, changes: { syncMode: mode } },
      { onSuccess: () => toast.success("Conversation sync updated."), onError: (error) => toast.error(requestFailureMessage(error)) },
    );
  const saveDays = () => {
    const next: SenderPolicy = { ...details.policy, inboxHistoryDays: days };
    savePolicy.mutate(next, { onSuccess: () => toast.success("Inbox history saved."), onError: (error) => toast.error(requestFailureMessage(error)) });
  };
  return (
    <div className="grid max-w-2xl gap-8">
      {!allowed && (
        <p role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm text-warning">
          Account access required. Only the person who connected this account can change what Synex reads from its inbox. Ask them to open this page, or send them a link to do it.
          <span className="mt-2 block"><Button size="sm" variant="outline" onClick={share}>Share with account owner</Button></span>
        </p>
      )}
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Which conversations Synex reads</h2>
        <SyncModeFields value={account.syncMode} onChange={changeSync} disabled={!allowed || actions.update.isPending} />
      </section>
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">How far back Synex reads</h2>
        <div className="grid max-w-xs gap-2">
          <label htmlFor={`${id}-days`} className="text-sm font-medium">Inbox history (days)</label>
          <Input id={`${id}-days`} type="number" min={1} max={3650} value={days} disabled={!allowed} onChange={(event) => setDays(Number(event.target.value))} />
        </div>
        <div>
          <Button size="sm" disabled={!allowed || days === details.policy.inboxHistoryDays || days < 1 || days > 3650} loading={savePolicy.isPending} onClick={saveDays}>Save history</Button>
        </div>
        <p className="text-xs text-muted-foreground">Reading messages never counts against this account's sending limits.</p>
      </section>
      {link && <ReconnectLinkDialog accountName={account.name} state={link} onRetry={share} onClose={() => setLink(null)} />}
    </div>
  );
}

export function HealthTab({ account, details }: { account: SenderAccount; details: AccountDetails }) {
  const accountId = account.id;
  const id = useId();
  const { savePolicy } = useManagementActions(accountId);
  const [days, setDays] = useState(details.policy.staleInviteDays);
  useEffect(() => setDays(details.policy.staleInviteDays), [details.policy.staleInviteDays]);
  const save = (change: Partial<SenderPolicy>) =>
    savePolicy.mutate({ ...details.policy, ...change }, { onSuccess: () => toast.success("Health settings saved."), onError: (error) => toast.error(requestFailureMessage(error)) });
  return (
    <div className="grid max-w-2xl gap-8">
      <section aria-labelledby={`${id}-summary`} className="grid gap-3">
        <h2 id={`${id}-summary`} className="text-base font-semibold">Health summary</h2>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Status</dt><dd><StatusBadge kind="account" status={account.status} /></dd></div>
          <div><dt className="text-muted-foreground">Last check</dt><dd className="font-medium">{account.lastCheckedAt ? formatRelative(account.lastCheckedAt) : "Never"}</dd></div>
          <div className="sm:col-span-2"><dt className="text-muted-foreground">Paused or restricted because</dt><dd className="font-medium">{account.pausedReason ?? "Nothing. No warning or restriction has been recorded."}</dd></div>
        </dl>
      </section>
      <section className="grid gap-3">
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-1">
            <h2 id={`${id}-withdraw`} className="text-base font-semibold">Auto-withdraw stale invitations</h2>
            <p className="text-sm text-muted-foreground">
              Old unanswered invitations count against you with LinkedIn. When this is on, Synex withdraws invitations that stay unanswered longer than the number of days below, a few at a time within this account's limits.
            </p>
          </div>
          <Switch aria-labelledby={`${id}-withdraw`} checked={details.policy.autoWithdraw} disabled={savePolicy.isPending} onCheckedChange={(checked) => save({ autoWithdraw: checked })} />
        </div>
        <div className="grid max-w-xs gap-2">
          <label htmlFor={`${id}-stale`} className="text-sm font-medium">Withdraw after (days)</label>
          <Input id={`${id}-stale`} type="number" min={7} max={365} value={days} onChange={(event) => setDays(Number(event.target.value))} />
        </div>
        <div>
          <Button size="sm" disabled={days === details.policy.staleInviteDays || days < 7 || days > 365} loading={savePolicy.isPending} onClick={() => save({ staleInviteDays: days })}>Save days</Button>
        </div>
        <p role="note" className="rounded-lg border border-border bg-surface-muted p-3 text-xs text-muted-foreground">
          Withdrawing runs a few at a time, only for invitations still pending, and counts against the "Invitation withdrawals" limit on the Limits tab (set it above 0 to allow it).
        </p>
      </section>
      <section aria-labelledby={`${id}-activity`} className="grid gap-2">
        <h2 id={`${id}-activity`} className="text-base font-semibold">Recent activity</h2>
        {details.activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">No activity has been recorded for this account yet.</p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {details.activity.slice(0, 20).map((item) => (
              <li key={item.id} className="flex flex-wrap gap-x-2">
                <span className="font-medium">{item.step.replaceAll("_", " ")}</span>
                <span className="text-muted-foreground">{item.status}{item.message ? `: ${item.message}` : ""}</span>
                <span className="ml-auto text-xs text-muted-foreground">{formatRelative(item.createdAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {details.health && (
        <section aria-labelledby="health-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="health-h" className="text-base font-semibold">Safety score</h2>
            <span data-testid="safety-score" className={`rounded-full px-3 py-1 text-sm font-semibold ${({ good: "bg-success-soft text-success", watch: "bg-warning-soft text-warning", risk: "bg-danger-soft text-danger" } as Record<string, string>)[details.health.level] ?? ""}`}>{details.health.score} · {details.health.label}</span>
            {details.health.acceptanceRate !== null && <span className="text-sm text-muted-foreground">{details.health.acceptanceRate}% of requests accepted in 30 days</span>}
          </div>
          <ul className="grid gap-1 text-sm">{details.health.advice.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      )}
      <section className="grid gap-2">
        <h2 className="text-base font-semibold">LinkedIn social selling score</h2>
        <p className="text-sm text-muted-foreground">
          {details.ssi === null ? details.ssiReason : `Score ${details.ssi}`} Synex never shows a made-up score.
        </p>
      </section>
    </div>
  );
}

export function AccountTab({ account, details }: { account: SenderAccount; details: AccountDetails }) {
  const { deactivate, remove } = useManagementActions(account.id);
  const actions = useAccountActions();
  const [confirm, setConfirm] = useState<"deactivate" | "disconnect" | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [typed, setTyped] = useState("");
  const navigate = useNavigate();
  const deactivated = details.lifecycle === "deactivated";
  return (
    <div className="grid max-w-2xl gap-8">
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Deactivate this seat</h2>
        <p className="text-sm text-muted-foreground">
          Stops everything on this account and frees its seat. Pending actions are cancelled. Its conversations, leads and history are kept, and you can connect it again later.
        </p>
        <div>
          <Button variant="outline" disabled={deactivated} onClick={() => setConfirm("deactivate")}>{deactivated ? "Seat deactivated" : "Deactivate seat"}</Button>
        </div>
      </section>
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Disconnect this account</h2>
        <p className="text-sm text-muted-foreground">
          Removes the saved LinkedIn session so Synex can no longer use the account. Your history stays. Your LinkedIn profile is not touched.
        </p>
        <div>
          <Button variant="outline" className="text-danger" disabled={account.status === "disconnected"} onClick={() => setConfirm("disconnect")}>Disconnect</Button>
        </div>
      </section>
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Delete this account</h2>
        <p className="text-sm text-muted-foreground">
          Removes this account from Synex for good: its saved session, its pending actions and its seat. Your LinkedIn profile is not touched. This cannot be undone; to use the profile again you connect it as a new account.
        </p>
        <div>
          <Button variant="destructive" onClick={() => { setTyped(""); setDeleting(true); }}>Delete account</Button>
        </div>
      </section>
      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{`Delete ${account.name}?`}</DialogTitle>
            <DialogDescription>This removes the account from Synex permanently. Type its name to confirm.</DialogDescription>
          </DialogHeader>
          <label htmlFor="delete-confirm" className="text-sm font-medium">Account name</label>
          <Input id="delete-confirm" value={typed} autoComplete="off" onChange={(event) => setTyped(event.target.value)} />
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setDeleting(false)}>Cancel</Button>
            <Button variant="destructive" disabled={typed.trim() !== account.name} loading={remove.isPending}
              onClick={() => remove.mutate(typed, { onSuccess: () => { toast.success(`${account.name} deleted.`); navigate("/linkedin-accounts"); }, onError: (error) => toast.error(requestFailureMessage(error)) })}>
              Delete permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={confirm === "deactivate"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={`Deactivate ${account.name}'s seat?`}
        description="Pending actions on this account are cancelled and its seat is freed. History is kept."
        confirmLabel="Deactivate seat"
        destructive
        loading={deactivate.isPending}
        onConfirm={() =>
          deactivate.mutate(undefined, {
            onSuccess: () => {
              toast.success("Seat deactivated.");
              setConfirm(null);
            },
            onError: (error) => toast.error(requestFailureMessage(error)),
          })
        }
      />
      <ConfirmDialog
        open={confirm === "disconnect"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={`Disconnect ${account.name}?`}
        description="Synex removes the saved LinkedIn session, so this account stops sending. It keeps the account's history."
        confirmLabel="Disconnect"
        destructive
        loading={actions.disconnect.isPending}
        onConfirm={() =>
          actions.disconnect.mutate(account.id, {
            onSuccess: () => {
              toast.success(`${account.name} disconnected.`);
              setConfirm(null);
            },
            onError: (error) => toast.error(requestFailureMessage(error)),
          })
        }
      />
    </div>
  );
}
