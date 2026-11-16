import { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { requestFailureMessage } from "../copy";
import { useAccountActions } from "../hooks";
import { useManagementActions, type AccountDetails, type SenderPolicy } from "../management";
import type { SenderAccount, SyncMode } from "../schemas";
import { SyncModeFields } from "../SyncModeFields";

export function PrivacyTab({ account, details }: { account: SenderAccount; details: AccountDetails }) {
  const id = useId();
  const actions = useAccountActions();
  const { savePolicy } = useManagementActions(account.id);
  const [days, setDays] = useState(details.policy.inboxHistoryDays);
  useEffect(() => setDays(details.policy.inboxHistoryDays), [details.policy.inboxHistoryDays]);
  const allowed = details.canChangePrivacy;
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
          Account access required. Only the person who connected this account can change what Synex reads from its inbox. Ask them to open this page, or to reconnect the account from the link in the account menu.
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
    </div>
  );
}

export function HealthTab({ accountId, details }: { accountId: string; details: AccountDetails }) {
  const id = useId();
  const { savePolicy } = useManagementActions(accountId);
  const [days, setDays] = useState(details.policy.staleInviteDays);
  useEffect(() => setDays(details.policy.staleInviteDays), [details.policy.staleInviteDays]);
  const save = (change: Partial<SenderPolicy>) =>
    savePolicy.mutate({ ...details.policy, ...change }, { onSuccess: () => toast.success("Health settings saved."), onError: (error) => toast.error(requestFailureMessage(error)) });
  return (
    <div className="grid max-w-2xl gap-8">
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
          The setting is saved, but withdrawing is not active yet: Synex does not withdraw any invitation until that part is built and verified. Nothing is withdrawn today.
        </p>
      </section>
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
  const { deactivate } = useManagementActions(account.id);
  const actions = useAccountActions();
  const [confirm, setConfirm] = useState<"deactivate" | "disconnect" | null>(null);
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
