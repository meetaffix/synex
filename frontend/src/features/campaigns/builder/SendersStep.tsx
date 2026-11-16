import { useState } from "react";
import { Link } from "react-router-dom";
import { SlidersHorizontal } from "lucide-react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { useOverview } from "@/features/linkedin-accounts/management";
import type { SenderAccount } from "@/features/linkedin-accounts/schemas";
import type { BuilderState } from "./model";

const SLICES = [
  { action: "send_invite", label: "Send connection request", max: 40 },
  { action: "send_message", label: "Send message", max: 100 },
  { action: "visit_profile", label: "View profile", max: 80 },
] as const;

/** Step 1. The builder never blocks on this: no sender simply shows up in the launch checklist. */
export function SendersStep({ state, set }: { state: BuilderState; set: (change: Partial<BuilderState>) => void }) {
  const accounts = useSenderAccounts();
  const overview = useOverview();
  const [allocating, setAllocating] = useState<SenderAccount | null>(null);
  const list = (accounts.data ?? []).filter((a) => a.status !== "disconnected");
  const chosen = state.accountIds;
  const toggle = (id: string) => set({ accountIds: chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id] });
  const allChecked = list.length > 0 && list.every((a) => chosen.includes(a.id));
  const total = chosen.reduce((sum, id) => sum + (overview.data?.accounts[id]?.connections.budget ?? 0), 0);

  return (
    <section aria-labelledby="senders-h" className="grid grid-cols-1 gap-4">
      <div>
        <h2 id="senders-h" className="text-lg font-semibold">LinkedIn senders</h2>
        <p className="text-sm text-muted-foreground">
          More senders mean more people reached each day. Leads are shared evenly between the senders you choose, and each sender keeps to its own daily limits.
        </p>
      </div>
      {accounts.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading your accounts.</p>}
      {accounts.data && list.length === 0 && (
        <p className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          You have no connected sender accounts yet. You can keep building, but the campaign cannot launch until one is connected.{" "}
          <Link className="underline underline-offset-2" to="/linkedin-accounts?connect=1">Connect an account</Link>.
        </p>
      )}
      {list.length > 0 && (
        <div role="region" tabIndex={0} aria-label="Sender accounts (scrolls sideways)" className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">Choose the sender accounts for this campaign</caption>
            <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="w-10 px-3 py-2"><Checkbox aria-label="Select all sender accounts" checked={allChecked} onCheckedChange={() => set({ accountIds: allChecked ? [] : list.map((a) => a.id) })} /></th>
                <th scope="col" className="px-3 py-2 font-medium">Account</th>
                <th scope="col" className="px-3 py-2 font-medium">Connections a day</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
                <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {list.map((a) => {
                const usage = overview.data?.accounts[a.id]?.connections;
                return (
                  <tr key={a.id} className="border-t border-border">
                    <td className="px-3 py-2"><Checkbox aria-label={`Use ${a.name}`} checked={chosen.includes(a.id)} onCheckedChange={() => toggle(a.id)} /></td>
                    <th scope="row" className="px-3 py-2 text-left font-medium">{a.name}</th>
                    <td className="px-3 py-2 tabular-nums">{usage ? `up to ${usage.high} (rolling 24 h)` : "Not set yet"}</td>
                    <td className="px-3 py-2"><StatusBadge kind="account" status={a.status} /></td>
                    <td className="flex flex-wrap justify-end gap-1 px-3 py-2">
                      <Button asChild size="sm" variant="ghost"><Link to={`/linkedin-accounts/${a.id}?tab=limits`}>View limits</Link></Button>
                      <Button size="icon-sm" variant="ghost" aria-label={`Reserve actions for this campaign on ${a.name}`} onClick={() => setAllocating(a)}><SlidersHorizontal /></Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p role="status" className="rounded-lg bg-primary-soft px-3 py-2 text-sm text-primary-soft-foreground" data-testid="sender-total">
        {chosen.length} account{chosen.length === 1 ? "" : "s"} selected. Total daily limit: {total} connections.
      </p>

      <Dialog open={!!allocating} onOpenChange={(open) => !open && setAllocating(null)}>
        <DialogContent className="max-w-md">
          {allocating && <AllocationForm account={allocating} state={state} set={set} onClose={() => setAllocating(null)} />}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function AllocationForm({ account, state, set, onClose }: { account: SenderAccount; state: BuilderState; set: (change: Partial<BuilderState>) => void; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(Object.fromEntries(SLICES.map((s) => [s.action, String(state.allocation[account.id]?.[s.action] ?? "")])));
  const save = () => {
    const row: Record<string, number> = {};
    for (const s of SLICES) {
      const text = values[s.action].trim();
      if (text !== "") row[s.action] = Math.max(0, Math.min(s.max, Math.floor(Number(text) || 0)));
    }
    const next = { ...state.allocation };
    if (Object.keys(row).length) next[account.id] = row;
    else delete next[account.id];
    set({ allocation: next });
    onClose();
  };
  return (
    <>
      <DialogHeader>
        <DialogTitle>Campaign action allocation</DialogTitle>
        <DialogDescription>
          Reserve part of {account.name}&apos;s day for this campaign. Capacity you do not reserve goes to older campaigns first. A reserved amount this campaign cannot use is wasted, so leave a field empty to share the sender&apos;s day freely.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-3">
        {SLICES.map((s) => (
          <div key={s.action} className="grid grid-cols-[1fr_6rem] items-center gap-3">
            <label htmlFor={`alloc-${s.action}`} className="text-sm font-medium">{s.label} <span className="text-xs text-muted-foreground">(maximum {s.max})</span></label>
            <Input id={`alloc-${s.action}`} type="number" min={0} max={s.max} value={values[s.action]} placeholder="Shared"
              onChange={(e) => setValues({ ...values, [s.action]: e.target.value })} />
          </div>
        ))}
      </div>
      <DialogFooter className="mt-2">
        <Button variant="outline" onClick={onClose}>Close</Button>
        <Button onClick={save}>Save allocations</Button>
      </DialogFooter>
    </>
  );
}
