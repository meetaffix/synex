import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/services/client";

export interface CampaignWebhook { webhookId: string | null; events: string[] }
interface Hook { id: string; kind: string; url: string; enabled: boolean }

const EVENTS: [string, string][] = [
  ["reply_received", "A lead replied"],
  ["connection_accepted", "A connection request was accepted"],
  ["lead_interested", "A conversation was marked interested"],
  ["campaign_launched", "This campaign was launched"],
  ["campaign_paused", "This campaign was paused"],
];

const host = (url: string) => { try { return new URL(url).host; } catch { return url; } };

/** Send this campaign's events to one of the workspace webhooks. The address, signing and safety checks stay on the webhook itself. */
export function WebhookDialog({ value, onSave, onClose }: { value: CampaignWebhook; onSave: (value: CampaignWebhook) => void; onClose: () => void }) {
  const hooks = useQuery({ queryKey: ["int", "hooks"], queryFn: () => api.get<Hook[]>("/integrations/webhooks"), retry: false, staleTime: 0, refetchOnMount: "always" });
  const [hookId, setHookId] = useState<string>(value.webhookId ?? "");
  const [events, setEvents] = useState<string[]>(value.events);
  const toggle = (id: string) => setEvents((now) => (now.includes(id) ? now.filter((e) => e !== id) : [...now, id]));
  const usable = (hooks.data ?? []).filter((h) => h.enabled);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Configure webhook</DialogTitle>
          <DialogDescription>Send this campaign&apos;s events to one of your webhooks, whatever events that webhook listens to on its own.</DialogDescription>
        </DialogHeader>
        {hooks.isLoading && <p role="status" className="text-sm text-muted-foreground">Loading your webhooks…</p>}
        {hooks.isError && <p role="alert" className="text-sm text-danger">Could not load your webhooks. Try again.</p>}
        {hooks.data && usable.length === 0 && (
          <p className="rounded-md bg-surface-muted p-3 text-sm">You have no enabled webhook yet. <Link className="font-medium underline" to="/settings/integrations?tab=webhooks">Add one in Integrations</Link>, then come back.</p>
        )}
        {usable.length > 0 && (
          <div className="grid gap-4">
            <div className="grid gap-1">
              <label htmlFor="camp-hook" className="text-sm font-medium">Webhook</label>
              <NativeSelect id="camp-hook" value={hookId} onChange={(e) => setHookId(e.target.value)}>
                <option value="">None: this campaign sends nothing to a webhook</option>
                {usable.map((h) => <option key={h.id} value={h.id}>{h.kind === "slack" ? "Slack" : "Webhook"}: {host(h.url)}</option>)}
              </NativeSelect>
            </div>
            <fieldset className="grid gap-2" disabled={!hookId}>
              <legend className="text-sm font-medium">Events to send</legend>
              {EVENTS.map(([id, label]) => (
                <label key={id} className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[rgb(var(--primary))]" checked={events.includes(id)} onChange={() => toggle(id)} /> {label}</label>
              ))}
            </fieldset>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={usable.length === 0 && !value.webhookId} onClick={() => { onSave({ webhookId: hookId || null, events: hookId ? events : [] }); onClose(); }}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
