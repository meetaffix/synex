import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { useCampaignList } from "@/features/campaigns/hooks";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";
import { INTEREST_LABEL, useInboxActions, type InboxItem } from "./model";

interface Overview {
  campaigns: { id: string; name: string; status: string; runStatus: string | null }[];
  doNotContact: string | null;
}

/** Who this is, what you have decided about the thread, and where the person is in your campaigns. */
export function ProfilePanel({ item, onClose }: { item: InboxItem; onClose: () => void }) {
  const actions = useInboxActions();
  const qc = useQueryClient();
  const [tag, setTag] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const overview = useQuery({ queryKey: ["inbox", "lead-overview", item.leadId], queryFn: () => api.get<Overview>(`/leads/${item.leadId}/overview`) });
  const campaigns = useCampaignList();
  const add = useMutation({
    mutationFn: () => api.post(`/leads/${item.leadId}/add-to-campaign`, { campaignId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbox", "lead-overview", item.leadId] }),
  });
  const run = (action: Parameters<typeof actions.bulk.mutate>[0]["action"], value?: string) =>
    actions.bulk.mutate({ ids: [item.id], action, value }, { onError: (e) => toast.error(requestFailureMessage(e)) });
  const choices = (campaigns.data ?? []).filter((c) => !overview.data?.campaigns.some((x) => x.id === c.id));

  return (
    <aside aria-label="Profile details" className="grid content-start gap-5 border-t border-border p-4 text-sm xl:border-l xl:border-t-0">
      <div className="flex items-start gap-3">
        <UserAvatar name={item.leadName} className="size-14" />
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold">{item.leadName}</h2>
          <p className="text-muted-foreground">{[item.leadTitle, item.leadCompany].filter(Boolean).join(" at ") || "No title"}</p>
          {item.linkedinUrl && <a className="underline-offset-2 hover:underline" href={item.linkedinUrl} target="_blank" rel="noreferrer noopener">View LinkedIn profile</a>}
        </div>
        <Button size="sm" variant="ghost" className="ml-auto xl:hidden" onClick={onClose}>Close profile details</Button>
      </div>
      <div>
        <Button size="sm" variant="outline" disabled title="Coming soon">Fetch profile (coming soon)</Button>
        <p className="mt-1 text-xs text-muted-foreground">Reading more of the profile needs the paced profile reader, which is not built yet. What Synex already knows is shown here.</p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="This conversation">
        <Button size="sm" variant="outline" aria-pressed={item.starred} onClick={() => run(item.starred ? "unstar" : "star")}>{item.starred ? "Starred" : "Mark as starred"}</Button>
        <Button size="sm" variant="outline" aria-pressed={item.answered} onClick={() => run(item.answered ? "unanswered" : "answered")}>{item.answered ? "Answered" : "Mark as answered"}</Button>
        <Button size="sm" variant="outline" onClick={() => run(item.status === "archived" ? "unarchive" : "archive")}>{item.status === "archived" ? "Unarchive" : "Archive"}</Button>
      </div>
      <div className="grid gap-1">
        <Label htmlFor="pp-interest">Interest</Label>
        <NativeSelect id="pp-interest" value={item.interest ?? ""} onChange={(e) => run("interest", e.target.value)}>
          <option value="">No label</option>
          {Object.entries(INTEREST_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </NativeSelect>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="pp-tag">Tags</Label>
        <ul aria-label="Tags on this conversation" className="flex flex-wrap gap-1">
          {item.tags.map((t) => <li key={t} className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs">{t}<button type="button" aria-label={`Remove tag ${t}`} className="px-1" onClick={() => run("tag_remove", t)}>×</button></li>)}
        </ul>
        <div className="flex gap-2">
          <Input id="pp-tag" value={tag} maxLength={40} placeholder="New tag" onChange={(e) => setTag(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && tag.trim()) { e.preventDefault(); run("tag_add", tag.trim()); setTag(""); } }} />
          <Button size="sm" variant="outline" disabled={!tag.trim()} onClick={() => { run("tag_add", tag.trim()); setTag(""); }}>Add tag</Button>
        </div>
      </div>
      <section aria-label="Lead overview" className="grid gap-2">
        <h3 className="font-semibold">Lead overview</h3>
        {overview.isLoading && <p className="text-muted-foreground">Loading.</p>}
        {overview.data?.doNotContact && <p role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-2 text-warning">On the do-not-contact list.</p>}
        {overview.data && overview.data.campaigns.length === 0 && <p className="text-muted-foreground">Lead not present in any campaign.</p>}
        <ul className="grid gap-1">{overview.data?.campaigns.map((c) => <li key={c.id}><span className="font-medium">{c.name}</span> <span className="text-muted-foreground">({c.status}{c.runStatus ? `, sequence ${c.runStatus}` : ""})</span></li>)}</ul>
        {overview.data && !overview.data.doNotContact && choices.length > 0 && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1"><Label htmlFor="pp-campaign">Add to a campaign</Label>
              <NativeSelect id="pp-campaign" value={campaignId} onChange={(e) => setCampaignId(e.target.value)}><option value="">Choose a campaign</option>{choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect></div>
            <Button size="sm" disabled={!campaignId} loading={add.isPending} onClick={() => add.mutate(undefined, { onSuccess: () => { toast.success("Added to the campaign's lead list."); setCampaignId(""); }, onError: (e) => toast.error(requestFailureMessage(e)) })}>Add</Button>
          </div>
        )}
      </section>
    </aside>
  );
}
