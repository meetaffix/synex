import { useState } from "react";
import { Settings, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { AiDrawer } from "./AiDrawer";
import { SequenceTemplates } from "./SequenceTemplates";
import { MessageField } from "./MessageField";
import { SmartGraph } from "./SmartGraph";
import { WebhookDialog } from "./WebhookDialog";
import { lostInClassic, toClassic } from "./graph";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MIN_WAIT_MINUTES, defaultAi, newStep, type AiConfig, type BuilderState, type BuilderStep } from "./model";

const TITLES: Record<string, string> = { connection_request: "Connection request", message: "Message", follow_up: "Follow-up message" };

interface Props {
  state: BuilderState;
  set: (change: Partial<BuilderState>) => void;
  campaignId: string;
  onOpenContext: () => void;
}

/** Step 3, the classic sequence: a straight line of actions. Settings are shown on every block, never hidden behind a click. */
export function SequenceStep({ state, set, campaignId, onOpenContext }: Props) {
  const [aiFor, setAiFor] = useState<BuilderStep | null>(null);
  const [templates, setTemplates] = useState(false);
  const [hook, setHook] = useState(false);
  const [switching, setSwitching] = useState<"smart" | "classic" | null>(null);
  const steps = state.steps;
  const patch = (key: number, change: Partial<BuilderStep>) => set({ steps: steps.map((s) => (s.key === key ? { ...s, ...change } : s)) });
  const addFollowUp = () => {
    const end = steps.findIndex((s) => s.type === "end");
    const at = end === -1 ? steps.length : end;
    const wait = { ...newStep("wait"), delayHours: 48 };
    set({ steps: [...steps.slice(0, at), wait, newStep("follow_up"), ...steps.slice(at)] });
  };
  // A follow-up is its wait plus its message. Moving it swaps that pair with the neighbouring follow-up, so waits keep their place in front.
  const followUps = steps.map((s, i) => ({ s, i })).filter((x) => x.s.type === "follow_up");
  const moveFollowUp = (index: number, direction: -1 | 1) => {
    const at = followUps.findIndex((f) => f.i === index);
    const other = followUps[at + direction];
    if (at < 0 || !other) return;
    const block = (i: number) => (steps[i - 1]?.type === "wait" ? [steps[i - 1], steps[i]] : [steps[i]]);
    const [first, second] = direction === -1 ? [other.i, index] : [index, other.i];
    const start = steps[first - 1]?.type === "wait" ? first - 1 : first;
    const end = second + 1;
    set({ steps: [...steps.slice(0, start), ...block(second), ...block(first), ...steps.slice(end)] });
  };
  const removeFollowUp = (index: number) => set({ steps: steps.filter((_, i) => i !== index && !(i === index - 1 && steps[i].type === "wait")) });
  const smart = state.mode === "smart";
  const lost = lostInClassic(steps);
  const switchTo = (mode: "smart" | "classic") => {
    if (mode === state.mode) return;
    if (mode === "classic" && lost.length === 0) set({ mode });
    else setSwitching(mode);
  };
  const hasMessage = steps.some((s) => s.type === "message");
  const firstMessageIndex = steps.findIndex((s) => s.type === "message");

  return (
    <section aria-labelledby="seq-h" className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="seq-h" className="text-lg font-semibold">Sequence</h2>
          <p className="text-sm text-muted-foreground">Synex views the profile, sends the connection request, then messages once the person accepts.</p>
        </div>
        <div role="group" aria-label="Sequence mode" className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setTemplates(true)}>Templates</Button>
          <Button size="sm" variant="outline" aria-label="Sequence settings: configure webhook" onClick={() => setHook(true)}><Settings aria-hidden /> Webhook{state.webhook.webhookId ? " on" : ""}</Button>
          <Button size="sm" variant={smart ? "outline" : "default"} aria-pressed={!smart} onClick={() => switchTo("classic")}>Classic</Button>
          <Button size="sm" variant={smart ? "default" : "outline"} aria-pressed={smart} onClick={() => switchTo("smart")}>Smart</Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{smart ? "Smart: add any action, and split the sequence with If steps. Each branch ends when it runs out of steps." : "Classic runs a straight sequence. Switch to Smart for branches and more actions."}</p>
      {smart && <SmartGraph state={state} set={set} campaignId={campaignId} onOpenContext={onOpenContext} />}
      {hook && <WebhookDialog value={state.webhook} onSave={(webhook) => set({ webhook })} onClose={() => setHook(false)} />}
      <Dialog open={switching !== null} onOpenChange={(open) => !open && setSwitching(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{switching === "smart" ? "Switch to Smart?" : "Switch to Classic?"}</DialogTitle>
            <DialogDescription>
              {switching === "smart" ? "Your steps stay exactly as they are. You can then add branches and more actions, such as voice notes, InMails and likes." : `Classic shows a straight line, so this removes ${lost.join(", ")}.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSwitching(null)}>Cancel</Button>
            <Button onClick={() => { if (switching === "classic") set({ mode: "classic", steps: toClassic(steps) }); else set({ mode: "smart" }); setSwitching(null); }}>{switching === "smart" ? "Switch to Smart" : "Switch and remove them"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {!smart && <ol className="grid gap-3" aria-label="Sequence steps">
        {steps.map((step, index) => {
          if (step.type === "end") return <li key={step.key} className="text-center text-xs text-muted-foreground">End of sequence</li>;
          if (step.type === "wait") {
            const before = steps[index - 1]?.type;
            const inMinutes = typeof step.config.minutes === "number";
            const days = !inMinutes && step.delayHours % 24 === 0 && step.delayHours >= 24;
            const minimum = before === "connection_request" ? 3 : 1;
            const unit = inMinutes ? "minutes" : days ? "days" : "hours";
            const shown = inMinutes ? Number(step.config.minutes) : days ? step.delayHours / 24 : step.delayHours;
            const chip = before === "connection_request" ? "If connected" : "If not replied";
            const setMinutes = (minutes: number) => { const m = Math.max(MIN_WAIT_MINUTES, Math.floor(minutes) || MIN_WAIT_MINUTES); patch(step.key, { delayHours: Math.max(1, Math.ceil(m / 60)), config: { ...step.config, minutes: m } }); };
            const setHours = (hours: number) => { const { minutes: _gone, ...rest } = step.config; patch(step.key, { delayHours: Math.max(minimum, hours), config: rest }); };
            return (
              <li key={step.key} className="grid gap-2 rounded-lg border border-dashed border-border p-3">
                <span className="w-fit rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-soft-foreground">{chip}</span>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <label htmlFor={`wait-${step.key}`}>Wait</label>
                  <Input id={`wait-${step.key}`} type="number" min={1} className="w-20" value={shown}
                    onChange={(e) => { const n = Math.floor(Number(e.target.value) || 1); if (unit === "minutes") setMinutes(n); else setHours(n * (unit === "days" ? 24 : 1)); }} />
                  <NativeSelect aria-label="Wait unit" className="w-auto" value={unit} onChange={(e) => {
                    const next = e.target.value;
                    if (next === "minutes") setMinutes(Math.max(MIN_WAIT_MINUTES, step.delayHours * 60));
                    else if (next === "days") setHours(Math.max(1, Math.round(step.delayHours / 24)) * 24);
                    else setHours(Math.max(minimum, step.delayHours));
                  }}>
                    {before !== "connection_request" && <option value="minutes">minutes</option>}
                    <option value="hours">hours</option>
                    <option value="days">days</option>
                  </NativeSelect>
                  <span className="text-xs text-muted-foreground">{unit === "minutes" ? `at least ${MIN_WAIT_MINUTES} minutes` : `at least ${minimum} ${minimum === 1 ? "hour" : "hours"}`}{before === "connection_request" ? " after the invitation is accepted" : ""}</span>
                </div>
              </li>
            );
          }
          const ai = step.aiConfig?.mode === "ai";
          const isFollowUp = step.type === "follow_up";
          return (
            <li key={step.key} className="grid gap-3 rounded-lg border border-border bg-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold">{step.type === "connection_request" ? "View profile and send connection request" : step.type === "message" && index === firstMessageIndex ? "Message 1" : TITLES[step.type]}</h3>
                {isFollowUp && (
                  <div className="flex flex-wrap items-center gap-1">
                    <Button size="sm" variant="ghost" aria-label="Move this follow-up earlier" disabled={followUps[0]?.i === index} onClick={() => moveFollowUp(index, -1)}>Move up</Button>
                    <Button size="sm" variant="ghost" aria-label="Move this follow-up later" disabled={followUps[followUps.length - 1]?.i === index} onClick={() => moveFollowUp(index, 1)}>Move down</Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => removeFollowUp(index)}>Remove</Button>
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {step.type === "connection_request" ? "A note is optional. LinkedIn allows up to 200 characters, and may send requests without a personalised note on some accounts." : isFollowUp ? "Sent only if the person has not replied." : "Sent after the connection is accepted."}
              </p>
              <MessageField label={ai ? `${TITLES[step.type]} (fallback text)` : `${TITLES[step.type]} text`} value={step.message} onChange={(message) => patch(step.key, { message })}
                templateCategory={step.type === "connection_request" ? "connection" : step.type === "follow_up" ? "follow_up" : "first_message"}
                maxLength={step.type === "connection_request" ? 200 : 1500} campaignId={campaignId} listId={state.leadListId} accountIds={state.accountIds}
                aiNote={ai ? "AI writes this for each person. You review every message before launch. This text is only a fallback." : undefined} />
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-muted p-3">
                <div className="grid gap-0.5">
                  <span id={`ai-${step.key}`} className="flex items-center gap-1 text-sm font-medium"><Sparkles className="size-4" aria-hidden /> Synex AI writing</span>
                  <span className="text-xs text-muted-foreground">{ai ? `On: ${step.aiConfig?.tone} tone, ${step.aiConfig?.strategy.replaceAll("_", " ")} strategy.` : "Write this message with AI for each person. Switch on to configure."}</span>
                </div>
                <div className="flex items-center gap-2">
                  {ai && <Button size="sm" variant="outline" onClick={() => setAiFor(step)}>Configure</Button>}
                  <Switch aria-labelledby={`ai-${step.key}`} checked={ai}
                    onCheckedChange={(on) => { if (on) setAiFor(step); else patch(step.key, { aiConfig: step.aiConfig ? ({ ...step.aiConfig, mode: "direct" } as AiConfig) : null }); }} />
                </div>
              </div>
            </li>
          );
        })}
      </ol>}
      {!smart && <div><Button variant="outline" onClick={addFollowUp} disabled={!hasMessage}>Add follow-up message</Button></div>}
      {!smart && !hasMessage && <p className="text-xs text-muted-foreground">Add a message to the sequence before adding follow-ups.</p>}

      {templates && <SequenceTemplates onApply={(steps) => set({ steps })} onClose={() => setTemplates(false)} />}
      {aiFor && (
        <AiDrawer title={aiFor.type === "connection_request" ? "the connection note" : `${TITLES[aiFor.type].toLowerCase()}`} stepType={aiFor.type} value={aiFor.aiConfig ?? { ...defaultAi(), mode: "ai" }} campaignId={campaignId}
          onSave={(value) => patch(aiFor.key, { aiConfig: value })} onClose={() => setAiFor(null)} onOpenContext={onOpenContext} />
      )}
    </section>
  );
}
