import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { draftsApi, STRATEGIES, TONES, defaultAi, type AiConfig, type StepType } from "./model";

const PROFILE_DATA: { key: string; label: string; built: boolean }[] = [
  { key: "role_company", label: "Current role and company", built: true },
  { key: "recent_posts", label: "Recent posts", built: false },
  { key: "skills", label: "Skills and endorsements", built: false },
  { key: "career", label: "Career transitions", built: false },
  { key: "interests", label: "Shared interests", built: false },
];
const SENDER_READS = ["How the sender talks", "Complete profile information", "Previous messages in the chat", "The complete campaign sequence"];

interface Props {
  title: string;
  stepType: StepType;
  value: AiConfig | null;
  campaignId: string;
  onSave: (value: AiConfig) => void;
  onClose: () => void;
  onOpenContext: () => void;
}

/** The per-message AI settings. Closing with changes asks first. Nothing here generates text except the Preview button, which shows its cost. */
export function AiDrawer({ title, stepType, value, campaignId, onSave, onClose, onOpenContext }: Props) {
  const [draft, setDraft] = useState<AiConfig>(value ?? { ...defaultAi(), mode: "ai" });
  const [tab, setTab] = useState<"direct" | "ai">(draft.mode);
  const [confirming, setConfirming] = useState(false);
  const initial = JSON.stringify(value ?? { ...defaultAi(), mode: "ai" });
  const dirty = JSON.stringify(draft) !== initial;
  const preview = useMutation({ mutationFn: () => draftsApi.preview(campaignId, stepType, { ...draft, mode: "ai" }), onError: (e) => toast.error(requestFailureMessage(e)) });

  const close = () => (dirty ? setConfirming(true) : onClose());
  const save = () => {
    onSave({ ...draft, mode: tab });
    onClose();
  };
  const set = (change: Partial<AiConfig>) => setDraft((d) => ({ ...d, ...change }));
  const insert = (token: string) => set({ instructions: `${draft.instructions}${draft.instructions && !draft.instructions.endsWith(" ") ? " " : ""}${token}` });

  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-h-[92vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{`Configure AI for ${title}`}</DialogTitle>
          <DialogDescription>Choose whether this message is written by you or by AI for each person.</DialogDescription>
        </DialogHeader>
        <Tabs label="How this message is written" tabs={[{ id: "direct", label: "Direct" }, { id: "ai", label: "AI assisted" }]} value={tab} idPrefix="aid" onChange={(next) => setTab(next as "direct" | "ai")} />
        <TabPanel id="direct" active={tab === "direct"} idPrefix="aid">
          <p className="text-sm text-muted-foreground">You write the message yourself in the editor. It is the same for everyone, with variables filled in. Use Preview there to see it.</p>
        </TabPanel>
        <TabPanel id="ai" active={tab === "ai"} idPrefix="aid">
          <div className="grid gap-5">
            <p className="rounded-lg border border-border bg-surface-muted p-3 text-sm">
              Synex AI also uses the campaign context you added.{" "}
              <Button type="button" variant="link" className="h-auto p-0" onClick={() => { onClose(); onOpenContext(); }}>Open AI campaign context</Button>
            </p>
            <section className="grid gap-2" aria-label="What the AI reads about each person">
              <h3 className="text-sm font-semibold">What the AI reads: per profile</h3>
              {PROFILE_DATA.map((p) => (
                <label key={p.key} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={!!draft.profile_data[p.key]} disabled={!p.built} onCheckedChange={(v) => set({ profile_data: { ...draft.profile_data, [p.key]: v === true } })} />
                  <span className={p.built ? "" : "text-muted-foreground"}>{p.label}{p.built ? "" : " (coming soon: needs the paced profile reader)"}</span>
                </label>
              ))}
            </section>
            <section className="grid gap-1" aria-label="What the AI reads about the sender">
              <h3 className="text-sm font-semibold">What the AI reads: per sender</h3>
              <ul className="list-disc pl-5 text-sm text-muted-foreground">{SENDER_READS.map((r) => <li key={r}>{r}</li>)}</ul>
              <p className="text-xs text-muted-foreground">Read-only. Only what you wrote in the campaign context and the sender&apos;s name and headline are used today.</p>
            </section>
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-semibold">Tone</legend>
              <div role="radiogroup" aria-label="Tone" className="flex flex-wrap gap-2">
                {TONES.map(([id, label]) => <Button key={id} type="button" role="radio" aria-checked={draft.tone === id} size="sm" variant={draft.tone === id ? "default" : "outline"} onClick={() => set({ tone: id })}>{label}</Button>)}
              </div>
            </fieldset>
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-semibold">Strategy</legend>
              <div role="radiogroup" aria-label="Strategy" className="flex flex-wrap gap-2">
                {STRATEGIES.map(([id, label]) => <Button key={id} type="button" role="radio" aria-checked={draft.strategy === id} size="sm" variant={draft.strategy === id ? "default" : "outline"} onClick={() => set({ strategy: id })}>{label}</Button>)}
              </div>
            </fieldset>
            <div className="grid gap-2">
              <Label htmlFor="ai-instructions">AI generation instructions (optional)</Label>
              <Textarea id="ai-instructions" rows={3} maxLength={2000} value={draft.instructions} onChange={(e) => set({ instructions: e.target.value })} />
              <div className="flex flex-wrap gap-2">
                {[["First name", "{{first_name}}"], ["Last name", "{{last_name}}"], ["Company", "{{company}}"]].map(([label, token]) => (
                  <Button key={token} type="button" size="sm" variant="outline" onClick={() => insert(token)}>{label}</Button>
                ))}
              </div>
            </div>
            <p role="note" className="text-sm text-muted-foreground">You review every message before the campaign launches. Nothing is written while sending.</p>
            <div className="grid gap-2">
              <Button type="button" variant="outline" className="w-fit" loading={preview.isPending} onClick={() => preview.mutate()}>Preview message</Button>
              {preview.data && (
                <div className="grid gap-2 rounded-lg border border-border bg-surface-muted p-3" aria-live="polite">
                  <p className="whitespace-pre-wrap text-sm">{preview.data.text}</p>
                  <p className="text-xs text-muted-foreground">
                    For {preview.data.leadName}, written by {preview.data.provider}. {preview.data.estimatedUsd > 0 ? `This preview cost about $${preview.data.estimatedUsd}.` : "This preview cost nothing."}
                  </p>
                  <Button type="button" size="sm" variant="ghost" className="w-fit" onClick={() => preview.mutate()}>Write another</Button>
                </div>
              )}
            </div>
          </div>
        </TabPanel>
        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={close}>Close</Button>
          <Button onClick={save}>Save</Button>
        </DialogFooter>
        {confirming && (
          <div role="alertdialog" aria-label="Unsaved changes" className="grid gap-3 rounded-lg border border-warning/40 bg-warning-soft p-4 text-sm">
            <p className="font-medium">Unsaved changes. Save them before closing?</p>
            <div className="flex gap-2"><Button size="sm" variant="outline" onClick={onClose}>Close without saving</Button><Button size="sm" onClick={save}>Save</Button></div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
