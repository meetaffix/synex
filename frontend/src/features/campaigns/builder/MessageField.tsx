import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shuffle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { api } from "@/services/client";
import { useTemplates } from "@/hooks/api";

export const VARIABLE_GROUPS: { label: string; names: string[] }[] = [
  { label: "Lead", names: ["first_name", "last_name", "company", "job_title", "location", "headline"] },
  { label: "From LinkedIn", names: ["linkedin_firstName", "linkedin_lastName", "linkedin_company", "linkedin_jobTitle", "linkedin_headline", "linkedin_location"] },
  { label: "Sender", names: ["sender_firstName", "sender_lastName", "sender_company", "sender_title"] },
];

/** Splits text into plain parts and {{variable}} chips so placeholders read as chips, not code. */
export function Chips({ text }: { text: string }) {
  const parts = text.split(/(\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\})/g);
  return (
    <p className="whitespace-pre-wrap break-words text-sm">
      {parts.map((part, i) => (/^\{\{/.test(part) ? <span key={i} className="rounded bg-primary-soft px-1 font-medium text-primary-soft-foreground">{part.replace(/[{}\s]/g, "")}</span> : <span key={i}>{part}</span>))}
    </p>
  );
}

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
  campaignId: string;
  listId: string | null;
  accountIds: string[];
  /** When set, the text is written by AI per person: the box is a fallback template and says so. */
  aiNote?: string;
  /** Which saved templates to offer: connection, first_message or follow_up. */
  templateCategory?: string;
}

export function MessageField({ label, value, onChange, maxLength, campaignId, listId, accountIds, aiNote, templateCategory }: Props) {
  const saved = useTemplates();
  const offered = (saved.data ?? []).filter((t) => !templateCategory || t.category === templateCategory);
  const id = useId();
  const area = useRef<HTMLTextAreaElement>(null);
  const [custom, setCustom] = useState("");
  const [previewing, setPreviewing] = useState(false);

  const insert = (text: string) => {
    const el = area.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(maxLength ? next.slice(0, maxLength) : next);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + text.length, start + text.length);
    });
  };
  const spintax = () => {
    const el = area.current;
    const chosen = el && el.selectionEnd > el.selectionStart ? value.slice(el.selectionStart, el.selectionEnd) : "";
    insert(chosen ? `{${chosen}|another way to say it}` : "{Hi|Hello|Hey}");
  };

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} ref={area} rows={4} value={value} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} aria-describedby={`${id}-help`} />
      <p id={`${id}-help`} className="text-xs text-muted-foreground">
        {aiNote ?? "Variables are filled in for each person. {Hi|Hello} picks one option at random."}
        {maxLength ? ` ${value.length} of ${maxLength} characters.` : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect aria-label={`Insert a variable into ${label}`} className="w-auto" value="" onChange={(e) => e.target.value && insert(`{{${e.target.value}}}`)}>
          <option value="">Insert variable</option>
          {VARIABLE_GROUPS.map((g) => (
            <optgroup key={g.label} label={g.label}>{g.names.map((n) => <option key={n} value={n}>{n}</option>)}</optgroup>
          ))}
        </NativeSelect>
        <NativeSelect aria-label={`Insert a saved template into ${label}`} className="w-auto" value="" onChange={(e) => { const t = offered.find((x) => x.id === e.target.value); if (t) onChange(maxLength ? t.body.slice(0, maxLength) : t.body); }}>
          <option value="">Insert template</option>
          {offered.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </NativeSelect>
        <Button type="button" size="sm" variant="outline" onClick={spintax}>Add spintax</Button>
        <div className="flex items-center gap-1">
          <input aria-label={`Custom variable name for ${label}`} value={custom} onChange={(e) => setCustom(e.target.value.replace(/[^A-Za-z0-9_]/g, ""))} placeholder="custom variable"
            className="h-8 w-36 rounded-md border border-input bg-surface px-2 text-sm" />
          <Button type="button" size="sm" variant="outline" disabled={!/^[A-Za-z]/.test(custom)} onClick={() => { insert(`{{${custom}}}`); setCustom(""); }}>Add</Button>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => setPreviewing(true)}>Preview</Button>
      </div>
      {value && <div aria-label={`${label} with variables marked`} className="rounded-md bg-surface-muted p-2"><Chips text={value} /></div>}
      {previewing && <PreviewDialog text={value} campaignId={campaignId} listId={listId} accountIds={accountIds} onClose={() => setPreviewing(false)} />}
    </div>
  );
}

function PreviewDialog({ text, campaignId, listId, accountIds, onClose }: { text: string; campaignId: string; listId: string | null; accountIds: string[]; onClose: () => void }) {
  const accounts = useSenderAccounts();
  const senders = (accounts.data ?? []).filter((a) => accountIds.includes(a.id));
  const leads = useQuery({ queryKey: ["preview-leads", listId], enabled: !!listId, queryFn: () => api.get<{ id: string; firstName: string; lastName: string }[]>(`/leads?listId=${listId}`) });
  const [leadId, setLeadId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [shuffle, setShuffle] = useState(0);
  const lead = leadId || leads.data?.[0]?.id || "";
  const sender = accountId || senders[0]?.id || "";
  const rendered = useQuery({
    queryKey: ["render", campaignId, text, lead, sender, shuffle],
    enabled: !!lead,
    queryFn: () => api.post<{ text: string; leadName: string; unresolved: string[] }>(`/campaigns/${campaignId}/drafts/render`, { text, leadId: lead, accountId: sender || undefined, shuffle }),
    retry: false,
  });
  useEffect(() => setShuffle(0), [text]);
  const nothing = !listId || (leads.data && leads.data.length === 0) || senders.length === 0;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Message preview</DialogTitle>
          <DialogDescription>How this message reads for one person from one sender. Nothing is sent.</DialogDescription>
        </DialogHeader>
        {nothing ? (
          <p className="rounded-lg border border-border p-4 text-sm text-muted-foreground">No data available. No accounts or leads found. Choose a sender and a lead list first.</p>
        ) : (
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor="pv-sender">Sender</Label>
                <NativeSelect id="pv-sender" value={sender} onChange={(e) => setAccountId(e.target.value)}>{senders.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</NativeSelect>
              </div>
              <div className="grid gap-1">
                <Label htmlFor="pv-lead">Lead</Label>
                <NativeSelect id="pv-lead" value={lead} onChange={(e) => setLeadId(e.target.value)}>{(leads.data ?? []).slice(0, 50).map((l) => <option key={l.id} value={l.id}>{`${l.firstName} ${l.lastName}`.trim()}</option>)}</NativeSelect>
              </div>
            </div>
            <div className="rounded-lg border border-border bg-surface-muted p-3" aria-live="polite">
              {rendered.isLoading && <p className="text-sm text-muted-foreground">Writing the preview.</p>}
              {rendered.data && <Chips text={rendered.data.text || "(empty message)"} />}
              {rendered.isError && <p role="alert" className="text-sm text-danger">The preview could not be made.</p>}
            </div>
            {rendered.data && rendered.data.unresolved.length > 0 && (
              <p role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm text-warning">
                This person has no value for {rendered.data.unresolved.map((v) => `{{${v}}}`).join(", ")}. It would be sent as written. Fill it in on the lead, or remove it.
              </p>
            )}
            <div><Button size="sm" variant="outline" onClick={() => setShuffle((n) => n + 1)}><Shuffle aria-hidden /> Show another choice</Button></div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
