import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { useCampaignList } from "../hooks";
import { api } from "@/services/client";
import { outline } from "./graph";
import { newStep, type BuilderStep, type StepType } from "./model";

type Plan = { type: StepType; message?: string; hours?: number }[];
interface Template { id: string; name: string; description: string; steps: Plan }

/** Four ready-made sequences. Messages use variables and are meant to be edited. */
export const BUNDLED: Template[] = [
  { id: "nurture", name: "New connection nurture", description: "A warm hello after they accept, then one gentle follow-up.", steps: [
    { type: "connection_request", message: "Hi {{first_name}}, I came across your work at {{company}} and would like to connect." }, { type: "wait", hours: 24 },
    { type: "message", message: "Thanks for connecting, {{first_name}}! What are you focused on at {{company}} this quarter?" }, { type: "wait", hours: 96 },
    { type: "follow_up", message: "Hi {{first_name}}, a quick follow-up in case my last note got buried. Happy to share what has worked for similar teams." }, { type: "end" }] },
  { id: "connect-convert", name: "5-step connect and convert", description: "Connect, welcome, value, reminder and a last short note.", steps: [
    { type: "connection_request", message: "Hi {{first_name}}, I work with people in your role at companies like {{company}}. Would be great to connect." }, { type: "wait", hours: 24 },
    { type: "message", message: "Thanks for connecting, {{first_name}}. I help teams like yours save time on outreach. Worth a short chat?" }, { type: "wait", hours: 72 },
    { type: "follow_up", message: "Hi {{first_name}}, sharing one idea that tends to help: start with a question, not a pitch. Want the short version?" }, { type: "wait", hours: 96 },
    { type: "follow_up", message: "Last note from me, {{first_name}}: if this is not a priority, no problem. Should I check back next quarter?" }, { type: "end" }] },
  { id: "cold", name: "Cold connection request", description: "Only a connection request with a short note. Nothing else.", steps: [
    { type: "connection_request", message: "Hi {{first_name}}, I enjoy following work in your field. Would be glad to connect." }, { type: "end" }] },
  { id: "playbook", name: "Full-cycle outreach playbook", description: "Connect, welcome, two follow-ups spaced over two weeks.", steps: [
    { type: "connection_request", message: "Hi {{first_name}}, your role at {{company}} caught my eye. I would like to connect." }, { type: "wait", hours: 24 },
    { type: "message", message: "Thanks for connecting, {{first_name}}! I would love to learn how you handle this at {{company}}." }, { type: "wait", hours: 120 },
    { type: "follow_up", message: "Hi {{first_name}}, following up on my note. Is this something you are looking at right now?" }, { type: "wait", hours: 168 },
    { type: "follow_up", message: "{{first_name}}, I will leave it here. If it becomes relevant, I am glad to help." }, { type: "end" }] },
];

const fromPlan = (plan: Plan): BuilderStep[] => plan.map((p) => ({ ...newStep(p.type), message: p.message ?? "", delayHours: p.hours ?? 0 }));

/** Start the sequence from a bundled template or from a campaign you made before. Applying replaces the current steps, so it asks first. */
export function SequenceTemplates({ onApply, onClose }: { onApply: (steps: BuilderStep[]) => void; onClose: () => void }) {
  const [tab, setTab] = useState("templates");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<{ name: string; steps: BuilderStep[] } | null>(null);
  const campaigns = useCampaignList();
  const shown = BUNDLED.filter((t) => t.name.toLowerCase().includes(query.toLowerCase()));
  const previous = (campaigns.data ?? []).filter((c) => c.name.toLowerCase().includes(query.toLowerCase()));

  const usePrevious = async (id: string, name: string) => {
    const data = await api.get<{ steps: { type: StepType; message: string | null; delayHours: number | null; aiConfig: BuilderStep["aiConfig"]; config?: Record<string, unknown> | null; parent?: number | null; branch?: "yes" | "no" | null }[] }>(`/campaigns/${id}/share`);
    const made = data.steps.map((s) => ({ ...newStep(s.type), message: s.message ?? "", delayHours: s.delayHours ?? 0, aiConfig: s.aiConfig ?? null, config: { ...newStep(s.type).config, ...(s.config ?? {}) } }));
    // A shared sequence names each step's parent by its position; give the copies their own parents and branches.
    data.steps.forEach((s, i) => { if (typeof s.parent === "number" && made[s.parent]) { made[i].parentKey = made[s.parent].key; made[i].branch = s.branch ?? null; } });
    setChosen({ name, steps: made });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Sequence templates</DialogTitle>
          <DialogDescription>Start from a ready-made sequence or one of your earlier campaigns. You can edit every step afterwards.</DialogDescription>
        </DialogHeader>
        <Tabs label="Template source" tabs={[{ id: "templates", label: "Templates" }, { id: "previous", label: "Previous campaigns" }]} value={tab} idPrefix="seqt" onChange={(t) => { setTab(t); setChosen(null); }} />
        <Input aria-label="Search templates" type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
        <TabPanel id="templates" active={tab === "templates"} idPrefix="seqt">
          <ul aria-label="Bundled templates" className="grid gap-2">
            {shown.map((t) => (
              <li key={t.id} className="grid gap-1 rounded-lg border border-border p-3">
                <span className="font-medium">{t.name}</span>
                <span className="text-sm text-muted-foreground">{t.description}</span>
                <span className="text-xs text-muted-foreground">{t.steps.filter((s) => s.type !== "wait" && s.type !== "end").length} messages over {Math.round(t.steps.reduce((h, s) => h + (s.hours ?? 0), 0) / 24)} days</span>
                <Button size="sm" variant="outline" className="w-fit" onClick={() => setChosen({ name: t.name, steps: fromPlan(t.steps) })}>{`Use ${t.name}`}</Button>
              </li>
            ))}
            {shown.length === 0 && <li className="text-sm text-muted-foreground">No template matches.</li>}
          </ul>
        </TabPanel>
        <TabPanel id="previous" active={tab === "previous"} idPrefix="seqt">
          <ul aria-label="Previous campaigns" className="grid gap-2">
            {previous.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
                <span className="font-medium">{c.name}</span>
                <Button size="sm" variant="outline" onClick={() => void usePrevious(c.id, c.name)}>{`Use ${c.name}`}</Button>
              </li>
            ))}
            {previous.length === 0 && <li className="text-sm text-muted-foreground">No earlier campaigns match.</li>}
          </ul>
        </TabPanel>
        {chosen && (
          <div role="alertdialog" aria-label="Replace the sequence" className="grid gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm">
            <p className="font-medium">Replace the current sequence with {chosen.name}?</p>
            <p>The messages you have written in this sequence will be replaced.</p>
            <pre aria-label="Preview of the sequence" className="max-h-48 overflow-auto rounded-md bg-surface p-2 text-xs">{outline(chosen.steps).join("\n")}</pre>
            <div className="flex gap-2"><Button size="sm" onClick={() => { onApply(chosen.steps); onClose(); }}>Apply template</Button><Button size="sm" variant="outline" onClick={() => setChosen(null)}>Cancel</Button></div>
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
