import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { INTEREST_LABEL, PRESETS, emptyFilter, useInboxMeta, type InboxFilter } from "./model";

interface Props {
  value: InboxFilter;
  onChange: (next: InboxFilter) => void;
}

/** Every inbox filter. Each one is a real server-side filter; nothing here is decoration. */
export function FilterPanel({ value, onChange }: Props) {
  const meta = useInboxMeta();
  const set = (change: Partial<InboxFilter>) => onChange({ ...value, ...change });
  const toggleCampaign = (id: string) => set({ campaigns: value.campaigns.includes(id) ? value.campaigns.filter((c) => c !== id) : [...value.campaigns, id] });
  const toggleAccount = (id: string) => set({ accounts: value.accounts.includes(id) ? value.accounts.filter((a) => a !== id) : [...value.accounts, id] });
  const flag = (key: keyof InboxFilter, label: string) => (
    <label key={key} className="flex items-center gap-2 text-sm">
      <Checkbox checked={!!value[key]} onCheckedChange={(v) => set({ [key]: v === true } as Partial<InboxFilter>)} /> {label}
    </label>
  );

  return (
    <section aria-label="Filter conversations" className="grid gap-4 border-b border-border p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Filter conversations</h2>
        <Button size="sm" variant="ghost" onClick={() => onChange({ ...emptyFilter(), q: value.q })}>Clear filters</Button>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Quick filters">
        <Button size="sm" aria-pressed={value.needsReply} variant={value.needsReply ? "default" : "outline"} onClick={() => set({ needsReply: !value.needsReply, iMessagedLast: false })}>Needs my reply</Button>
        <Button size="sm" aria-pressed={value.iMessagedLast} variant={value.iMessagedLast ? "default" : "outline"} onClick={() => set({ iMessagedLast: !value.iMessagedLast, needsReply: false })}>I messaged last</Button>
      </div>
      <fieldset className="grid gap-2">
        <legend className="mb-1 font-medium">Status</legend>
        {flag("starred", "Starred")}
        {flag("drafts", "Drafts")}
        {flag("scheduled", "Scheduled")}
        {flag("unread", "Unread")}
        {flag("archived", "Archived")}
      </fieldset>
      <div className="grid gap-1">
        <Label htmlFor="f-tag">Tag</Label>
        <NativeSelect id="f-tag" value={value.tag} onChange={(e) => set({ tag: e.target.value })}>
          <option value="">Any tag</option>
          {(meta.data?.tags ?? []).map((t) => <option key={t} value={t}>{t}</option>)}
        </NativeSelect>
      </div>
      <div className="grid gap-1">
        <Label htmlFor="f-interest">Interest</Label>
        <NativeSelect id="f-interest" value={value.interest} onChange={(e) => set({ interest: e.target.value })}>
          <option value="">Any interest</option>
          {Object.entries(INTEREST_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </NativeSelect>
      </div>
      <fieldset className="grid gap-2">
        <legend className="mb-1 font-medium">Sender accounts</legend>
        {(meta.data?.accounts ?? []).map((a) => (
          <label key={a.id} className="flex items-center gap-2"><Checkbox checked={value.accounts.includes(a.id)} onCheckedChange={() => toggleAccount(a.id)} /> {a.name}</label>
        ))}
      </fieldset>
      <fieldset className="grid gap-2">
        <legend className="mb-1 font-medium">Campaigns</legend>
        <NativeSelect aria-label="Include or exclude the chosen campaigns" value={value.campaignMode} onChange={(e) => set({ campaignMode: e.target.value as "include" | "exclude" })}>
          <option value="include">Include</option>
          <option value="exclude">Exclude</option>
        </NativeSelect>
        {(meta.data?.campaigns ?? []).map((c) => (
          <label key={c.id} className="flex items-center gap-2"><Checkbox checked={value.campaigns.includes(c.id)} onCheckedChange={() => toggleCampaign(c.id)} /> {c.name}</label>
        ))}
        {meta.data?.campaigns.length === 0 && <p className="text-muted-foreground">No campaigns yet.</p>}
      </fieldset>
      <div className="grid gap-1">
        <Label htmlFor="f-where">Include campaign conversations where</Label>
        <NativeSelect id="f-where" value={value.where} onChange={(e) => set({ where: e.target.value as InboxFilter["where"] })}>
          <option value="">Anything</option>
          <option value="messages_sent">Messages were sent</option>
          <option value="responses">The person responded</option>
        </NativeSelect>
      </div>
      <div className="grid gap-1">
        <Label htmlFor="f-date">Date</Label>
        <NativeSelect id="f-date" value={value.preset} onChange={(e) => set({ preset: e.target.value })}>
          {PRESETS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </NativeSelect>
        {value.preset === "custom" && (
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-1"><Label htmlFor="f-from">From</Label><Input id="f-from" type="date" value={value.dateFrom} onChange={(e) => set({ dateFrom: e.target.value })} /></div>
            <div className="grid gap-1"><Label htmlFor="f-to">To</Label><Input id="f-to" type="date" value={value.dateTo} onChange={(e) => set({ dateTo: e.target.value })} /></div>
          </div>
        )}
      </div>
    </section>
  );
}
