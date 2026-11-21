import { useEffect, useState, type ReactElement } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Eye, Flag, GitBranch, Heart, Mail, Maximize2, MessageSquare, Mic, Minimize2, Plus, Send, Timer, Trash2, UserMinus, UserPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { MessageField } from "./MessageField";
import { VoiceNoteFields } from "./VoiceNoteFields";
import { addNode, addProblem, DESCRIPTIONS, isClosed, isConditional, LABELS, listOf, MENU, problems, removeNode } from "./graph";
import { type Branch, type BuilderState, type BuilderStep, type StepType } from "./model";

interface Props {
  state: BuilderState;
  set: (change: Partial<BuilderState>) => void;
  campaignId: string;
  /** Every lead is already a connection: a connection request is not offered and one already in the sequence is flagged. */
  audienceConnections?: boolean;
  /** The campaign is sending: wiping the whole sequence is not offered, because people are on its steps right now. */
  running?: boolean;
}

const ONCE_ACTIONS: StepType[] = ["profile_visit", "follow", "like_post", "withdraw_invite"];

/* ---- Canvas layout and node types ---- */
const STEP_W = 250, STEP_H = 68, ADD_W = 140, ADD_H = 38, VGAP = 56, HGAP = 36;
const ICONS: Partial<Record<StepType, typeof Send>> = {
  connection_request: UserPlus, message: MessageSquare, follow_up: MessageSquare, voice_note: Mic, inmail: Mail, free_inmail: Mail,
  profile_visit: Eye, follow: UserPlus, like_post: Heart, withdraw_invite: UserMinus, wait: Timer, if_connected: GitBranch, if_active: GitBranch, end: Flag,
};
/** Messages are teal, profile actions blue, timing and conditions amber: the map reads at a glance without reading every card. */
const TONES: Record<string, string> = {
  message: "bg-primary-soft text-primary-soft-foreground",
  profile: "bg-info-soft text-info",
  timing: "bg-warning-soft text-warning",
  end: "bg-surface-muted text-muted-foreground",
};
const toneOf = (type: StepType): string =>
  ["connection_request", "message", "follow_up", "voice_note", "inmail", "free_inmail"].includes(type) ? TONES.message
  : ["profile_visit", "follow", "like_post", "withdraw_invite"].includes(type) ? TONES.profile
  : type === "end" ? TONES.end : TONES.timing;

const branchLabel = (type: StepType, b: Branch) => (type === "if_connected" ? (b === "yes" ? "Connected" : "Not connected") : b === "yes" ? "Active" : "Not active");

const ONCE_NOTE: Partial<Record<StepType, string>> = { profile_visit: "Opens their profile", follow: "Follows them", like_post: "Likes their latest post", withdraw_invite: "Takes back the invitation", end: "The sequence stops here" };

function summary(s: BuilderStep): string {
  if (s.type === "wait") return s.delayHours >= 24 && s.delayHours % 24 === 0 ? `${s.delayHours / 24} days` : `${s.delayHours} hours`;
  if (s.type === "if_connected") return `Waits up to ${Number(s.config.waitDays ?? 15)} days`;
  if (s.type === "if_active") return `Active in the last ${Number(s.config.days ?? 30)} days`;
  if (s.aiConfig?.mode === "ai") return "Written by Synex AI";
  if (s.type === "voice_note") return s.config.audioId ? "Audio ready" : "Audio not set";
  if (["connection_request", "message", "follow_up", "inmail", "free_inmail"].includes(s.type)) return s.message.trim() ? s.message.trim().slice(0, 60) : "No text yet";
  return ONCE_NOTE[s.type] ?? "The sequence stops here";
}

interface StepData extends Record<string, unknown> { step: BuilderStep; issue: string | null; open: () => void }
interface AddData extends Record<string, unknown> { menu: ReactElement | null }

function StepNode({ data }: NodeProps<Node<StepData>>) {
  const { step, issue, open } = data;
  const Icon = ICONS[step.type] ?? Send;
  return (
    <div style={{ width: STEP_W, height: STEP_H }}>
      <Handle type="target" position={Position.Top} className="!border-0 !bg-border" isConnectable={false} />
      <button type="button" onClick={open}         className={`nodrag flex h-full w-full items-center gap-3 rounded-lg border bg-surface px-3 text-left shadow-raised transition-[border-color,box-shadow,transform] duration-150 hover:-translate-y-px hover:border-primary hover:shadow-float focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${issue ? "border-danger" : "border-border"}`}>
        <span className={`grid size-9 shrink-0 place-items-center rounded-md ${toneOf(step.type)}`}><Icon className="size-4" aria-hidden /></span>
        <span className="min-w-0"><span className="block truncate text-sm font-semibold">{LABELS[step.type]}</span><span className={`block truncate text-xs ${issue ? "text-danger" : "text-muted-foreground"}`}>{issue ?? summary(step)}</span><span className="sr-only">Open settings</span></span>
      </button>
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-border" isConnectable={false} />
    </div>
  );
}
function StartNode() {
  return (
    <div className="flex h-[44px] w-[180px] items-center justify-center gap-2 rounded-full border border-border bg-surface text-sm font-semibold shadow-sm">
      <Send className="size-4" aria-hidden /> Campaign start
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-border" isConnectable={false} />
    </div>
  );
}
function AddNode({ data }: NodeProps<Node<AddData>>) {
  return (
    <div style={{ width: ADD_W, height: ADD_H }} className="nodrag flex items-center justify-center">
      <Handle type="target" position={Position.Top} className="!border-0 !bg-border" isConnectable={false} />
      {data.menu ?? <span className="text-xs text-muted-foreground">Then end</span>}
    </div>
  );
}
const NODE_TYPES = { step: StepNode, start: StartNode, add: AddNode };

/** Positions the tree top to bottom; each If step splits its width between its two branches. */
function layout(steps: BuilderStep[], issues: { key: number; message: string }[], open: (key: number) => void, addAction: (parent: number | null, branch: Branch | null) => ReactElement | null) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const edge = (source: string, target: string, label?: string): Edge => ({ id: `${source}-${target}`, source, target, type: "smoothstep", label, markerEnd: { type: MarkerType.ArrowClosed }, style: { strokeWidth: 1.5 }, labelStyle: { fontSize: 12, fontWeight: 600 } });
  const width = (parent: number | null, branch: Branch | null): number => {
    let w = Math.max(STEP_W, ADD_W);
    for (const s of listOf(steps, parent, branch)) if (isConditional(s.type)) w = Math.max(w, width(s.key, "yes") + HGAP + width(s.key, "no"));
    return w;
  };
  const place = (parent: number | null, branch: Branch | null, cx: number, y: number, prev: string, label?: string): number => {
    const list = listOf(steps, parent, branch);
    let pending = label;
    for (const s of list) {
      const id = `s${s.key}`;
      nodes.push({ id, type: "step", position: { x: cx - STEP_W / 2, y }, data: { step: s, issue: issues.find((p) => p.key === s.key)?.message ?? null, open: () => open(s.key) } satisfies StepData });
      edges.push(edge(prev, id, pending));
      pending = undefined; prev = id; y += STEP_H + VGAP;
      if (isConditional(s.type)) {
        const wy = width(s.key, "yes"), wn = width(s.key, "no");
        const total = wy + HGAP + wn;
        const a = place(s.key, "yes", cx - total / 2 + wy / 2, y, id, branchLabel(s.type, "yes"));
        const b = place(s.key, "no", cx + total / 2 - wn / 2, y, id, branchLabel(s.type, "no"));
        return Math.max(a, b);
      }
    }
    const id = `add-${parent ?? "root"}-${branch ?? "main"}`;
    nodes.push({ id, type: "add", position: { x: cx - ADD_W / 2, y }, data: { menu: addAction(parent, branch) } satisfies AddData });
    edges.push(edge(prev, id, pending));
    return y + ADD_H;
  };
  nodes.push({ id: "start", type: "start", position: { x: -90, y: 0 }, data: {} });
  place(null, null, 0, 44 + VGAP, "start");
  return { nodes, edges };
}

/** The Smart sequence: a tree of actions with If steps that split into two branches. Every node shows its settings on its card. */
export function SmartGraph({ state, set, campaignId, audienceConnections = false, running = false }: Props) {
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const [full, setFull] = useState(false);
  const [clearing, setClearing] = useState(false);
  const steps = state.steps;
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
                    <span className="grid"><span>{LABELS[type]}</span><span className="text-xs text-muted-foreground">{why ?? DESCRIPTIONS[type]}</span></span>
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
            aiNote={ai ? "This campaign was set up with AI writing per person. You review every message before launch." : undefined} />
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

  const selected = steps.find((s) => s.key === selectedKey) ?? null;
  const { nodes, edges } = layout(steps, issues, (key) => setSelectedKey(key), addAction);

  const canvas = (
    <div className={full ? "fixed inset-0 z-50 grid grid-rows-[auto_1fr] gap-2 bg-background p-4" : "grid gap-2"} {...(full ? { role: "region", "aria-label": "Sequence graph, full screen" } : {})}>
      <div role="toolbar" aria-label="Graph tools" className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" size="sm" variant="outline" onClick={() => setFull(!full)}>{full ? <><Minimize2 aria-hidden /> Exit full screen</> : <><Maximize2 aria-hidden /> Full screen</>}</Button>
        {!running && <Button type="button" size="sm" variant="outline" className="text-danger" disabled={steps.length === 0} onClick={() => setClearing(true)}><Trash2 aria-hidden /> Clear all</Button>}
      </div>
      <div className={`${full ? "min-h-0" : "h-[680px]"} overflow-hidden rounded-lg border border-border bg-surface-muted`} role="region" aria-label="Sequence graph canvas">
        <ReactFlowProvider>
          <ReactFlow key={nodes.length} nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1 }} minZoom={0.3} maxZoom={1.5}
            nodesDraggable={false} nodesConnectable={false} elementsSelectable zoomOnScroll={false} preventScrolling={false} proOptions={{ hideAttribution: true }}
            colorMode={document.documentElement.classList.contains("dark") ? "dark" : "light"}>
            <Background gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
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
      <DialogPrimitive.Root open={!!selected} onOpenChange={(o) => !o && setSelectedKey(null)}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-[60] bg-overlay/40" />
          <DialogPrimitive.Content className="fixed inset-y-0 right-0 z-[60] flex w-[min(520px,100vw)] flex-col gap-4 overflow-y-auto border-l border-border bg-surface p-5 shadow-float">
            {selected && (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <DialogPrimitive.Title className="text-lg font-semibold">Configure {LABELS[selected.type].toLowerCase()}</DialogPrimitive.Title>
                    <DialogPrimitive.Description className="text-sm text-muted-foreground">Changes apply to the sequence at once. Save the draft when you are done.</DialogPrimitive.Description>
                  </div>
                  <DialogPrimitive.Close className="grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-surface-muted" aria-label="Close settings"><X className="size-4" aria-hidden /></DialogPrimitive.Close>
                </div>
                {nodeBody(selected)}
                {issues.find((p) => p.key === selected.key) && <p role="status" className="text-xs text-danger">{issues.find((p) => p.key === selected.key)?.message}</p>}
                <div className="mt-auto flex justify-between gap-2 border-t border-border pt-4">
                  <Button variant="ghost" className="text-danger" onClick={() => { set({ steps: removeNode(steps, selected.key) }); setSelectedKey(null); }}><Trash2 aria-hidden /> Remove step</Button>
                  <Button onClick={() => setSelectedKey(null)}>Done</Button>
                </div>
              </>
            )}
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </div>
  );
}
