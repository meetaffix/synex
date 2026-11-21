import { AddToRunningDialog } from "@/features/campaigns/AddToRunningDialog";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useCampaignList } from "@/features/campaigns/hooks";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api, ApiError } from "@/services/client";
import { formatRelative } from "@/utils/format";
import type { Lead } from "@/types";

const overviewSchema = z.object({
  campaigns: z.array(z.object({ id: z.string(), name: z.string(), status: z.string(), runStatus: z.string().nullable(), stopReason: z.string().nullable() })),
  events: z.array(z.object({ type: z.string(), detail: z.string().nullable(), createdAt: z.string(), campaign: z.string().nullable() })),
  doNotContact: z.string().nullable(),
});

/** One lead: where it is in campaigns, what has happened to it, and a way to put it in a campaign. */
export function LeadOverviewDialog({ lead, onClose }: { lead: Lead | null; onClose: () => void }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["lead-overview", lead?.id],
    enabled: !!lead,
    queryFn: async () => {
      const result = overviewSchema.safeParse(await api.get(`/leads/${lead?.id}/overview`));
      if (!result.success) throw new ApiError(0, "The server sent a response Synex could not read. Try again.");
      return result.data;
    },
  });
  const campaigns = useCampaignList();
  const [campaignId, setCampaignId] = useState("");
  const [asking, setAsking] = useState(false); // a running campaign starts the person at once, so the screen asks first
  const add = useMutation({
    mutationFn: (confirmSend?: boolean) => api.post<{ added: boolean; started: boolean }>(`/leads/${lead?.id}/add-to-campaign`, { campaignId, ...(confirmSend ? { confirmSend: true } : {}) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lead-overview", lead?.id] }),
  });
  const choices = (campaigns.data ?? []).filter((c) => !query.data?.campaigns.some((x) => x.id === c.id));
  const variables = Object.entries(lead?.variables ?? {});

  return (
    <Dialog open={!!lead} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{lead ? `${lead.firstName} ${lead.lastName}` : "Lead"}</DialogTitle>
          <DialogDescription>{lead?.headline || [lead?.jobTitle, lead?.company].filter(Boolean).join(" at ") || "No headline"}</DialogDescription>
        </DialogHeader>
        {query.isLoading && <Skeleton className="h-24 w-full" />}
        {query.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(query.error)}</p>}
        {query.data && lead && (
          <div className="grid gap-5 text-sm">
            {query.data.doNotContact && (
              <p role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-warning">
                On the do-not-contact list ({query.data.doNotContact === "company" ? "their company is listed" : "this person is listed"}). Synex will never contact them.
              </p>
            )}
            <dl className="grid gap-1 sm:grid-cols-2">
              <div><dt className="text-muted-foreground">Status</dt><dd className="font-medium capitalize">{lead.status.replace("_", " ")}</dd></div>
              <div><dt className="text-muted-foreground">Source</dt><dd className="font-medium">{lead.source ?? "Added by hand"}</dd></div>
              <div><dt className="text-muted-foreground">Location</dt><dd className="font-medium">{lead.location || "Not known"}</dd></div>
              <div><dt className="text-muted-foreground">Company</dt><dd className="font-medium">{lead.company || "Not known"}</dd></div>
            </dl>
            {variables.length > 0 && (
              <section aria-label="Campaign variables">
                <h3 className="mb-1 font-semibold">Campaign variables</h3>
                <ul className="grid gap-1">{variables.map(([name, value]) => <li key={name}><code>{`{{${name}}}`}</code> is {value}</li>)}</ul>
              </section>
            )}
            <section aria-label="Campaigns">
              <h3 className="mb-1 font-semibold">Campaigns</h3>
              {query.data.campaigns.length === 0 ? (
                <p className="text-muted-foreground">Lead not present in any campaign.</p>
              ) : (
                <ul className="grid gap-1">
                  {query.data.campaigns.map((c) => (
                    <li key={c.id}><span className="font-medium">{c.name}</span> <span className="text-muted-foreground">({c.status}{c.runStatus ? `, sequence ${c.runStatus}` : ""}{c.stopReason ? `, stopped: ${c.stopReason.replaceAll("_", " ")}` : ""})</span></li>
                  ))}
                </ul>
              )}
              {!query.data.doNotContact && choices.length > 0 && (
                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <div className="grid gap-1">
                    <Label htmlFor="add-campaign">Add to a campaign</Label>
                    <NativeSelect id="add-campaign" value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
                      <option value="">Choose a campaign</option>
                      {choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </NativeSelect>
                  </div>
                  <Button size="sm" disabled={!campaignId} loading={add.isPending}
                    onClick={() => add.mutate(undefined, { onSuccess: (r) => { toast.success(r.started ? "Added. Their sequence starts within the campaign's limits." : "Added to the campaign's lead list."); setCampaignId(""); }, onError: (e) => (e instanceof ApiError && e.code === "send_confirmation_required" ? setAsking(true) : toast.error(requestFailureMessage(e))) })}>
                    Add
                  </Button>
                </div>
              )}
            </section>
            <section aria-label="History">
              <h3 className="mb-1 font-semibold">History</h3>
              {query.data.events.length === 0 ? (
                <p className="text-muted-foreground">Nothing has happened to this lead yet.</p>
              ) : (
                <ul className="grid gap-1">
                  {query.data.events.map((e, i) => (
                    <li key={i} className="flex flex-wrap gap-x-2">
                      <span className="font-medium">{e.type.replaceAll("_", " ")}</span>
                      <span className="text-muted-foreground">{[e.campaign, e.detail].filter(Boolean).join(": ")}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{formatRelative(e.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </DialogContent>
      {asking && lead && (
        <AddToRunningDialog open onOpenChange={(o) => !o && setAsking(false)} campaignId={campaignId} leadName={`${lead.firstName} ${lead.lastName}`.trim()} loading={add.isPending}
          onConfirm={() => add.mutate(true, { onSuccess: () => { toast.success("Added. Their sequence starts within the campaign's limits."); setCampaignId(""); setAsking(false); }, onError: (e) => { setAsking(false); toast.error(requestFailureMessage(e)); } })} />
      )}
    </Dialog>
  );
}
