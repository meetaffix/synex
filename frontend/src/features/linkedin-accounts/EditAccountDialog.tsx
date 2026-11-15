import { useId, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProxyInput } from "./ProxyInput";
import type { SenderAccount } from "./schemas";
import type { AccountChanges } from "./service";
import { SyncModeFields } from "./SyncModeFields";

const MIN_LIMIT = 0;

interface Props {
  account: SenderAccount;
  saving: boolean;
  error?: string;
  onSave: (changes: AccountChanges) => void;
  onClose: () => void;
}

export function EditAccountDialog({ account, saving, error, onSave, onClose }: Props) {
  const id = useId();
  const [limit, setLimit] = useState(String(account.dailyActionLimit));
  const [proxy, setProxy] = useState("");
  const [removeProxy, setRemoveProxy] = useState(false);
  const [syncMode, setSyncMode] = useState(account.syncMode);
  const [limitProblem, setLimitProblem] = useState<string>();
  const { ceilings } = account;
  const maxLimit = ceilings.dailyActions;
  const paused = limit.trim() !== "" && Number(limit) === 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = Number(limit);
    if (!Number.isInteger(value) || value < MIN_LIMIT || value > maxLimit) {
      setLimitProblem(`Enter a whole number from ${MIN_LIMIT} to ${maxLimit}. 0 pauses the account.`);
      return;
    }
    setLimitProblem(undefined);
    const changes: AccountChanges = {};
    if (value !== account.dailyActionLimit) changes.dailyActionLimit = value;
    if (proxy) changes.proxyUrl = proxy;
    else if (removeProxy) changes.proxyUrl = null;
    if (syncMode !== account.syncMode) changes.syncMode = syncMode;
    if (Object.keys(changes).length === 0) onClose();
    else onSave(changes);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader className="space-y-2">
          <DialogTitle className="text-xl">Edit {account.name}</DialogTitle>
          <DialogDescription>Change how much this account sends, how it syncs and the proxy it uses.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-6" noValidate aria-busy={saving}>
          <fieldset disabled={saving} className="grid gap-6 border-0 p-0">
          <div className="grid gap-2">
            <div className="flex items-baseline justify-between gap-3">
              <Label htmlFor={`${id}-limit`}>Daily action limit</Label>
              <span id={`${id}-limit-ceiling`} className="text-xs text-muted-foreground tabular-nums">
                Ceiling {maxLimit} a day
              </span>
            </div>
            <Input
              id={`${id}-limit`}
              type="number"
              inputMode="numeric"
              min={MIN_LIMIT}
              max={maxLimit}
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              aria-invalid={!!limitProblem}
              aria-describedby={`${id}-limit-ceiling ${id}-limit-help`}
              className="tabular-nums"
              autoFocus
            />
            <p id={`${id}-limit-help`} className={limitProblem ? "text-xs text-danger" : "text-xs text-muted-foreground"}>
              {limitProblem ??
                (paused
                  ? "Paused for this action: the account sends nothing until you raise the limit."
                  : "0 pauses the account. Lower limits are safer for LinkedIn accounts. Synex also ramps new accounts up gradually.")}
            </p>
            <p className="text-xs text-muted-foreground">
              Hard ceilings per account, whatever the limits say: {ceilings.connectionRequestsPerDay} connection requests a day
              ({ceilings.connectionRequestsPerWeek} a week), {ceilings.messagesPerDay} messages, {ceilings.profileVisitsPerDay} profile
              visits and {ceilings.followsPerDay} follows a day.
            </p>
          </div>
          <div className="grid gap-2">
            <h3 className="text-sm font-medium">Conversation sync</h3>
            <SyncModeFields value={syncMode} onChange={setSyncMode} disabled={!account.canChangeSyncMode} />
          </div>
          <div className="grid gap-2">
            <h3 className="text-sm font-medium">Proxy</h3>
            <ProxyInput
              value={proxy}
              onChange={(url) => {
                setProxy(url);
                if (url) setRemoveProxy(false);
              }}
              configured={account.proxyConfigured}
              onClear={() => setRemoveProxy(account.proxyConfigured)}
            />
          </div>
          </fieldset>
          <p role="status" aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
            {saving ? "Saving changes…" : ""}
          </p>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Save changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
