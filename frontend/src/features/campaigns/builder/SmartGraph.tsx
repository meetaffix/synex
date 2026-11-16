import { useEffect, useState, type ReactElement } from "react";
import { GitBranch, Maximize2, Minimize2, Plus, Sparkles, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { AiDrawer } from "./AiDrawer";
import { MessageField } from "./MessageField";
import { VoiceNoteFields } from "./VoiceNoteFields";
import { addNode, addProblem, isClosed, isConditional, LABELS, listOf, MENU, problems, removeNode } from "./graph";
import { defaultAi, type AiConfig, type Branch, type BuilderState, type BuilderStep, type StepType } from "./model";

interface Props {
  state: BuilderState;
  set: (change: Partial<BuilderState>) => void;
  campaignId: string;
  onOpenContext: () => void;
}

const ZOOMS = [0.6, 0.75, 1, 1.25, 1.5];
const ONCE_ACTIONS: StepType[] = ["profile_visit", "follow", "like_post", "withdraw_invite"];

/** The Smart sequence: a tree of actions with If steps that split into two branches. Every node shows its settings on its card. */
export function SmartGraph({ state, set, campaignId, onOpenContext }: Props) {
  const [zoom, setZoom] = useState(2);
  const [full, setFull] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [aiFor, setAiFor] = useState<BuilderStep | null>(null);
  const steps = state.steps;
  const audienceConnections = false;
  const issues = problems(steps, audienceConnections);
  const patch = (key: number, change: Partial<BuilderStep>) => set({ steps: steps.map((s) => (s.key === key ? { ...s, ...change } : s)) });
  const config = (s: BuilderStep, change: Record<string, unknown>) => patch(s.key, { config: { ...s.config, ...change } });

  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector("[role=dialog],[role=menu]")) setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  // Plain render functions, not components: a component defined here would be a new type on every render and remount its inputs while someone types.
  const addAction = (parentKey: number | null, branch: Branch | null) => {
    const list = listOf(steps, parentKey, branch);
    if (isClosed(list)) return null;
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" size="sm" variant="outline" aria-label={parentKey === null ? "Add action to the sequence" : `Add action to the ${branch === "yes" ? "yes" : "no"} branch`}><Plus aria-hidden /> Add action</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-h-80 overflow-y-auto">
          {MENU.map((group) => (
            <DropdownMenuGroup key={group.group}>
              <DropdownMenuLabel>{group.group}</DropdownMenuLabel>
              {group.types.map((type) => {
                const why = addProblem(steps, type, parentKey, branch, audienceConnections);
                return (
                  <DropdownMenuItem key={type} disabled={!!why} onSelect={() => set({ steps: addNode(steps, type, parentKey, branch) })}>
                    <span className="grid"><span>{LABELS[type]}</span>{why && <span className="text-xs text-muted-foreground">{why}</span>}</span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuGroup>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  const nodeBody = (s: BuilderStep) => {
    const ai = s.aiConfig?.mode === "ai";
    const id = `node-${s.key}`;
    if (s.type === "connection_request" || s.type === "message" || s.type === "follow_up" || s.type === "inmail" || s.type === "free_inmail") {
      const isInmail = s.type === "inmail" || s.type === "free_inmail";
      const label = LABELS[s.type];
      return (
        <div className="grid gap-3">
          {isInmail && (
            <div className="grid gap-1">
              <label htmlFor={`${id}-subject`} className="text-sm font-medium">InMail subject</label>
              <Input id={`${id}-subject`} maxLength={200} value={String(s.config.subject ?? "")} onChange={(e) => config(s, { subject: e.target.value })} />
              {s.type === "free_inmail" && <p className="text-xs text-muted-foreground">Sent only to open profiles. If the profile does not offer a free message, the person is skipped and the run stops with a reason.</p>}
              {s.type === "inmail" && <p className="text-xs text-muted-foreground">Uses one InMail credit from the sender&apos;s LinkedIn plan. If there are none left, the run stops with a reason.</p>}
            </div>
          )}
          <MessageField label={ai ? `${label} (fallback text)` : `${label} text`} value={s.message} onChange={(message) => patch(s.key, { message })}
            templateCategory={s.type === "connection_request" ? "connection" : s.type === "follow_up" ? "follow_up" : "first_message"}
            maxLength={s.type === "connection_request" ? 200 : 1500} campaignId={campaignId} listId={state.leadListId} accountIds={state.accountIds}
            aiNote={ai ? "AI writes this for each person. You review every message before launch. This text is only a fallback." : undefined} />
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-muted p-3">
              <div className="grid gap-0.5">
                <span id={`${id}-ai`} className="flex items-center gap-1 text-sm font-medium"><Sparkles className="size-4" aria-hidden /> Synex AI writing</span>
                <span className="text-xs text-muted-foreground">{ai ? `On: ${s.aiConfig?.tone} tone, ${s.aiConfig?.strategy.replaceAll("_", " ")} strategy.` : "Write this with AI for each person. Switch on to configure."}</span>
              </div>
              <div className="flex items-center gap-2">
                {ai && <Button size="sm" variant="outline" onClick={() => setAiFor(s)}>Configure</Button>}
                <Switch aria-labelledby={`${id}-ai`} checked={ai} onCheckedChange={(on) => { if (on) setAiFor(s); else patch(s.key, { aiConfig: s.aiConfig ? ({ ...s.aiConfig, mode: "direct" } as AiConfig) : null }); }} />
              </div>
          </div>
        </div>
      );
    }
    if (s.type === "voice_note") return <VoiceNoteFields id={id} config={s.config} onChange={(c) => patch(s.key, { config: c })} campaignId={campaignId} accountIds={state.accountIds} />;
    if (s.type === "wait") {
      const days = s.delayHours % 24 === 0 && s.delayHours >= 24;
      const shown = days ? s.delayHours / 24 : s.delayHours;
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor={`${id}-wait`}>Wait</label>
          <Input id={`${id}-wait`} type="number" min={1} className="w-20" value={shown} onChange={(e) => patch(s.key, { delayHours: Math.max(1, Math.floor(Number(e.target.value) || 1)) * (days ? 24 : 1) })} />
          <NativeSelect aria-label="Wait unit" className="w-auto" value={days ? "days" : "hours"} onChange={(e) => patch(s.key, { delayHours: e.target.value === "days" ? Math.max(1, Math.round(s.delayHours / 24)) * 24 : s.delayHours })}>
            <option value="hours">hours</option><option value="days">days</option>
          </NativeSelect>
        </div>
      );
    }
    if (s.type === "if_connected") {
      return (
        <div className="grid gap-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={`${id}-days`}>Wait up to</label>
            <Input id={`${id}-days`} type="number" min={1} max={30} className="w-20" value={Number(s.config.waitDays ?? 15)} onChange={(e) => config(s, { waitDays: Math.min(30, Math.max(1, Math.floor(Number(e.target.value) || 1))) })} />
            <span>days for the invitation to be accepted</span>
          </div>
          <p className="text-xs text-muted-foreground">Accepted in time: the Connected branch. Not accepted in time: the Not connected branch. Acceptance is checked slowly, within the sender&apos;s limits.</p>
        </div>
      );
    }
    if (s.type === "if_active") {
      return (
        <div className="grid gap-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={`${id}-active`}>Active means activity in the last</label>
            <Input id={`${id}-active`} type="number" min={1} max={365} className="w-20" value={Number(s.config.days ?? 30)} onChange={(e) => config(s, { days: Math.min(365, Math.max(1, Math.floor(Number(e.target.value) || 1))) })} />
            <span>days</span>
          </div>
          <p className="text-xs text-muted-foreground">Synex counts a reply, a message or an accepted invitation it has recorded. LinkedIn&apos;s own activity signal is not read.</p>
        </div>
      );
    }
    if (ONCE_ACTIONS.includes(s.type)) {
      const note: Partial<Record<StepType, string>> = {
        profile_visit: "Opens the person's profile once. Counts toward the sender's profile-view limit.",
        follow: "Follows the person once. Counts toward the follow limit.",
        like_post: "Likes the person's most recent post once. Skipped if they have no posts. Counts toward the like limit.",
        withdraw_invite: "Takes back the invitation if it is still pending. Does nothing if the person has accepted.",
      };
      return <p className="text-sm text-muted-foreground">{note[s.type]}</p>;
    }
    return null;
  };

  const nodeList = (parentKey: number | null, branch: Branch | null): ReactElement => {
    const list = listOf(steps, parentKey, branch);
    return (
      <ol className="grid gap-3 border-l-2 border-border pl-3 sm:pl-4" aria-label={parentKey === null ? "Main sequence" : branch === "yes" ? "Yes branch" : "No branch"}>
        {list.map((s) => {
          const issue = issues.find((p) => p.key === s.key);
          const conditional = isConditional(s.type);
          return (
            <li key={s.key} className="grid gap-3">
              <article aria-label={LABELS[s.type]} className="grid gap-3 rounded-lg border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="flex items-center gap-2 text-base font-semibold">{conditional && <GitBranch className="size-4" aria-hidden />}{LABELS[s.type]}</h3>
                  <Button size="sm" variant="ghost" className="text-danger" aria-label={`Remove ${LABELS[s.type]}`} onClick={() => set({ steps: removeNode(steps, s.key) })}><Trash2 aria-hidden /> Remove</Button>
                </div>
                {nodeBody(s)}
                {issue && <p role="status" className="text-xs text-danger">{issue.message}</p>}
              </article>
              {conditional && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {(["yes", "no"] as const).map((b) => (
                    <section key={b} aria-label={`${s.type === "if_connected" ? (b === "yes" ? "Connected" : "Not connected") : b === "yes" ? "Active" : "Not active"} branch`} className="grid min-w-0 gap-2 rounded-lg bg-surface-muted p-3">
                      <h4 className="text-sm font-semibold">{s.type === "if_connected" ? (b === "yes" ? "Connected" : "Not connected") : b === "yes" ? "Active" : "Not active"}</h4>
                      {nodeList(s.key, b)}
                      <div className="flex flex-wrap items-center gap-2">{addAction(s.key, b)}<span className="text-xs text-muted-foreground">Then end</span></div>
                    </section>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    );
  };

  const scale = ZOOMS[zoom];
  const canvas = (
    <div className={full ? "fixed inset-0 z-50 overflow-auto bg-background p-4" : "grid gap-3"} {...(full ? { role: "region", "aria-label": "Sequence graph, full screen" } : {})}>
      <div role="toolbar" aria-label="Graph tools" className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" aria-label="Zoom out" disabled={zoom === 0} onClick={() => setZoom(zoom - 1)}><ZoomOut aria-hidden /></Button>
        <span role="status" className="min-w-12 text-center text-sm" aria-label="Zoom level">{Math.round(scale * 100)}%</span>
        <Button type="button" size="sm" variant="outline" aria-label="Zoom in" disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom(zoom + 1)}><ZoomIn aria-hidden /></Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setFull(!full)}>{full ? <><Minimize2 aria-hidden /> Exit full screen</> : <><Maximize2 aria-hidden /> Full screen</>}</Button>
        <Button type="button" size="sm" variant="outline" className="text-danger" disabled={steps.length === 0} onClick={() => setClearing(true)}><Trash2 aria-hidden /> Clear all</Button>
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Sequence graph canvas">
        <div style={{ transform: `scale(${scale})`, transformOrigin: "0 0", width: `${100 / scale}%` }} className="grid gap-3">
          <div className="w-fit rounded-full bg-primary-soft px-3 py-1 text-sm font-medium text-primary-soft-foreground">Campaign start</div>
          {nodeList(null, null)}
          <div className="flex flex-wrap items-center gap-2">{addAction(null, null)}<span className="text-xs text-muted-foreground">Then end</span></div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="grid gap-3">
      {canvas}
      {issues.length > 0 && (
        <div role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm">
          <p className="font-medium">{issues.length === 1 ? "One node is not ready" : `${issues.length} nodes are not ready`}</p>
          <ul className="list-disc pl-5">{issues.map((p) => <li key={p.key}>{p.message}</li>)}</ul>
        </div>
      )}
      <Dialog open={clearing} onOpenChange={setClearing}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Clear the whole sequence?</DialogTitle><DialogDescription>Every node and branch is removed. This cannot be undone here.</DialogDescription></DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClearing(false)}>Keep it</Button>
            <Button variant="destructive" onClick={() => { set({ steps: [] }); setClearing(false); }}>Clear all</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {aiFor && (
        <AiDrawer title={LABELS[aiFor.type].toLowerCase()} stepType={aiFor.type} value={aiFor.aiConfig ?? { ...defaultAi(), mode: "ai" }} campaignId={campaignId}
          onSave={(value) => patch(aiFor.key, { aiConfig: value })} onClose={() => setAiFor(null)} onOpenContext={onOpenContext} />
      )}
    </div>
  );
}
