import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

type Context = Record<string, unknown>;
const LIMIT = 5000;
const TEMPLATES: Record<string, string> = {
  "Book a Demo": "Goal: book a 20-minute demo.\nAudience: heads of sales at small software companies.\nOffer: a live walkthrough of how we cut manual prospecting.\nValue: teams save hours a week and reach more of the right people.",
  "Webinar Promo": "Goal: fill seats for our next webinar.\nAudience: people who work in the topic.\nOffer: a free 45-minute webinar with a Q&A.\nValue: practical steps they can use the same week.",
  "Free Audit": "Goal: offer a free audit of their current setup.\nAudience: owners and managers who run this process today.\nOffer: a short written audit with three concrete fixes.\nValue: they keep the findings even if they do not hire us.",
  "Agency Pitch": "Goal: start a conversation about a project.\nAudience: marketing leads who hire outside help.\nOffer: a first call to understand their goals.\nValue: clear scope and pricing after one conversation.",
};
const text = (c: Context, key: string) => (typeof c[key] === "string" ? (c[key] as string) : "");
const list = (c: Context, key: string) => (Array.isArray(c[key]) ? (c[key] as string[]) : []);

/** The campaign's shared knowledge for AI messages and AI replies. Only what you write here is given to the AI. */
export function ContextPanel({ value, onSave, onClose }: { value: Context; onSave: (value: Context) => void; onClose: () => void }) {
  const [ctx, setCtx] = useState<Context>(value);
  const [tab, setTab] = useState("upload");
  const [website, setWebsite] = useState(text(value, "website"));
  const [showSite, setShowSite] = useState(!!text(value, "website"));
  const [avoid, setAvoid] = useState("");
  const set = (key: string, v: unknown) => setCtx((c) => ({ ...c, [key]: v }));

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 5_000_000) return void toast.error("Choose a file smaller than 5 MB.");
    if (!/\.(txt|md)$/i.test(file.name)) return void toast.error("Only .txt and .md files can be read for now. Paste the text of a PDF or Word file into the Context tab.");
    set("goals", (await file.text()).slice(0, LIMIT));
    toast.success("The file's text was added to Goals, audience, offer and value. Review it in the Context tab.");
    setTab("context");
  };
  const addAvoid = () => {
    const word = avoid.trim();
    if (word && !list(ctx, "do_not_mention").includes(word)) set("do_not_mention", [...list(ctx, "do_not_mention"), word.slice(0, 200)]);
    setAvoid("");
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>AI campaign context</DialogTitle>
          <DialogDescription>Shared knowledge for the AI messages and AI replies in this campaign. The AI uses only what you write here, and never invents facts.</DialogDescription>
        </DialogHeader>
        <Tabs label="Context sections" tabs={[{ id: "upload", label: "Upload" }, { id: "context", label: "Context" }, { id: "guardrails", label: "Guardrails" }]} value={tab} idPrefix="ctx" onChange={setTab} />
        <TabPanel id="upload" active={tab === "upload"} idPrefix="ctx">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="ctx-file">Add a file (.txt or .md, up to 5 MB)</Label>
              <input id="ctx-file" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(e) => { void readFile(e.target.files?.[0]); e.target.value = ""; }} />
              <p className="text-xs text-muted-foreground">PDF and Word files are not read yet. Paste their text into the Context tab instead, or choose Enter manually.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => setTab("context")}>Enter manually</Button>
              {!showSite && <Button type="button" variant="ghost" onClick={() => setShowSite(true)}>Add website</Button>}
            </div>
            {showSite && (
              <div className="grid gap-2">
                <Label htmlFor="ctx-site">Website address</Label>
                <Input id="ctx-site" value={website} placeholder="https://example.com" onChange={(e) => setWebsite(e.target.value)} />
                <p className="text-xs text-muted-foreground">Saved with the context so you remember the source. Synex does not read the site for you yet: paste what matters into the Context tab.</p>
                <div className="flex gap-2">
                  <Button type="button" size="sm" disabled={!/^https?:\/\/\S+$/.test(website)} onClick={() => { set("website", website); setShowSite(true); toast.success("Website saved."); }}>Continue</Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => { setShowSite(false); setWebsite(""); set("website", ""); }}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        </TabPanel>
        <TabPanel id="context" active={tab === "context"} idPrefix="ctx">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="ctx-goals">Goals, audience, offer and value</Label>
              <div className="flex flex-wrap gap-2">{Object.keys(TEMPLATES).map((name) => <Button key={name} type="button" size="sm" variant="outline" onClick={() => set("goals", TEMPLATES[name])}>{name}</Button>)}</div>
              <Textarea id="ctx-goals" rows={6} maxLength={LIMIT} value={text(ctx, "goals")} onChange={(e) => set("goals", e.target.value)} />
              <p className="text-xs text-muted-foreground">{text(ctx, "goals").length} of {LIMIT} characters.</p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ctx-link">Campaign meeting link (overrides the sender&apos;s calendar link)</Label>
              <Input id="ctx-link" value={text(ctx, "meeting_link")} onChange={(e) => set("meeting_link", e.target.value)} />
            </div>
            {([["qualification_questions", "Qualification questions"], ["proof_points", "Proof points"], ["objections", "Common objections and answers"]] as const).map(([key, label]) => (
              <div key={key} className="grid gap-2">
                <Label htmlFor={`ctx-${key}`}>{label}</Label>
                <Textarea id={`ctx-${key}`} rows={3} maxLength={LIMIT} value={text(ctx, key)} onChange={(e) => set(key, e.target.value)} />
              </div>
            ))}
          </div>
        </TabPanel>
        <TabPanel id="guardrails" active={tab === "guardrails"} idPrefix="ctx">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="ctx-avoid">Do not mention</Label>
              <div className="flex gap-2">
                <Input id="ctx-avoid" value={avoid} placeholder="a word or phrase" onChange={(e) => setAvoid(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addAvoid(); } }} />
                <Button type="button" variant="outline" disabled={!avoid.trim()} onClick={addAvoid}>Add</Button>
              </div>
              <ul aria-label="Phrases the AI must not mention" className="flex flex-wrap gap-2">
                {list(ctx, "do_not_mention").map((word) => (
                  <li key={word} className="flex items-center gap-1 rounded-full bg-surface-muted px-2 py-1 text-sm">{word}
                    <button type="button" aria-label={`Remove ${word}`} className="rounded px-1 text-muted-foreground hover:text-foreground" onClick={() => set("do_not_mention", list(ctx, "do_not_mention").filter((w) => w !== word))}>×</button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ctx-notes">Additional notes</Label>
              <Textarea id="ctx-notes" rows={4} maxLength={LIMIT} value={text(ctx, "notes")} onChange={(e) => set("notes", e.target.value)} />
            </div>
          </div>
        </TabPanel>
        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <Button onClick={() => { onSave(ctx); onClose(); }}>Save AI settings</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
