import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { AiDrawer } from "./AiDrawer";
import { MessageField } from "./MessageField";
import { defaultAi, newStep, type AiConfig, type BuilderState, type BuilderStep } from "./model";

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
  const steps = state.steps;
  const patch = (key: number, change: Partial<BuilderStep>) => set({ steps: steps.map((s) => (s.key === key ? { ...s, ...change } : s)) });
  const addFollowUp = () => {
    const end = steps.findIndex((s) => s.type === "end");
    const at = end === -1 ? steps.length : end;
    const wait = { ...newStep("wait"), delayHours: 48 };
    set({ steps: [...steps.slice(0, at), wait, newStep("follow_up"), ...steps.slice(at)] });
  };
  const removeFollowUp = (index: number) => set({ steps: steps.filter((_, i) => i !== index && !(i === index - 1 && steps[i].type === "wait")) });
  const hasMessage = steps.some((s) => s.type === "message");
  const firstMessageIndex = steps.findIndex((s) => s.type === "message");

  return (
    <section aria-labelledby="seq-h" className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="seq-h" className="text-lg font-semibold">Sequence</h2>
          <p className="text-sm text-muted-foreground">Synex views the profile, sends the connection request, then messages once the person accepts.</p>
        </div>
        <div role="group" aria-label="Sequence mode" className="flex gap-2">
          <Button size="sm" aria-pressed="true">Classic</Button>
          <Button size="sm" variant="outline" disabled aria-describedby="smart-soon">Smart</Button>
        </div>
      </div>
      <p id="smart-soon" className="text-xs text-muted-foreground">Smart (a branching graph) is not built yet. Classic runs a straight sequence.</p>

      <ol className="grid gap-3" aria-label="Sequence steps">
        {steps.map((step, index) => {
          if (step.type === "end") return <li key={step.key} className="text-center text-xs text-muted-foreground">End of sequence</li>;
          if (step.type === "wait") {
            const days = step.delayHours % 24 === 0 && step.delayHours >= 24;
            const before = steps[index - 1]?.type;
            const minimum = before === "connection_request" ? 3 : 1;
            const unit = days ? "days" : "hours";
            const shown = days ? step.delayHours / 24 : step.delayHours;
            const chip = before === "connection_request" ? "If connected" : "If not replied";
            return (
              <li key={step.key} className="grid gap-2 rounded-lg border border-dashed border-border p-3">
                <span className="w-fit rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-soft-foreground">{chip}</span>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <label htmlFor={`wait-${step.key}`}>Wait</label>
                  <Input id={`wait-${step.key}`} type="number" min={1} className="w-20" value={shown}
                    onChange={(e) => patch(step.key, { delayHours: Math.max(minimum, Math.floor(Number(e.target.value) || 1) * (unit === "days" ? 24 : 1)) })} />
                  <NativeSelect aria-label="Wait unit" className="w-auto" value={unit} onChange={(e) => patch(step.key, { delayHours: Math.max(minimum, (e.target.value === "days" ? Math.max(1, Math.round(step.delayHours / 24)) * 24 : Math.max(minimum, step.delayHours))) })}>
                    <option value="hours">hours</option>
                    <option value="days">days</option>
                  </NativeSelect>
                  <span className="text-xs text-muted-foreground">at least {minimum} {minimum === 1 ? "hour" : "hours"}{before === "connection_request" ? " after the invitation is accepted" : ""}</span>
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
                {isFollowUp && <Button size="sm" variant="ghost" className="text-danger" onClick={() => removeFollowUp(index)}>Remove</Button>}
              </div>
              <p className="text-xs text-muted-foreground">
                {step.type === "connection_request" ? "A note is optional. LinkedIn allows up to 200 characters, and may send requests without a personalised note on some accounts." : isFollowUp ? "Sent only if the person has not replied." : "Sent after the connection is accepted."}
              </p>
              <MessageField label={ai ? `${TITLES[step.type]} (fallback text)` : `${TITLES[step.type]} text`} value={step.message} onChange={(message) => patch(step.key, { message })}
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
      </ol>
      <div><Button variant="outline" onClick={addFollowUp} disabled={!hasMessage}>Add follow-up message</Button></div>
      {!hasMessage && <p className="text-xs text-muted-foreground">Add a message to the sequence before adding follow-ups.</p>}

      {aiFor && (
        <AiDrawer title={aiFor.type === "connection_request" ? "the connection note" : `${TITLES[aiFor.type].toLowerCase()}`} stepType={aiFor.type} value={aiFor.aiConfig ?? { ...defaultAi(), mode: "ai" }} campaignId={campaignId}
          onSave={(value) => patch(aiFor.key, { aiConfig: value })} onClose={() => setAiFor(null)} onOpenContext={onOpenContext} />
      )}
    </section>
  );
}
