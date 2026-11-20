import { newStep, type Branch, type BuilderStep, type StepType } from "./model";

/** The Smart sequence is a tree held as a flat list: a step names the If step it hangs under and its branch. A list is the main sequence or one branch. */

export const CONDITIONALS: StepType[] = ["if_connected", "if_active"];
export const isConditional = (t: StepType) => CONDITIONALS.includes(t);

export const LABELS: Record<StepType, string> = {
  connection_request: "Send connection request",
  message: "Send message",
  follow_up: "Send follow-up",
  voice_note: "Send voice note",
  inmail: "Send InMail",
  free_inmail: "Send free InMail",
  profile_visit: "View profile",
  follow: "Follow profile",
  like_post: "Like a post",
  withdraw_invite: "Withdraw invite",
  wait: "Wait",
  if_connected: "If connection",
  if_active: "Is active on LinkedIn",
  end: "End",
};

/** One plain line per action, shown in the Add action menu so nobody has to guess what a step does. */
export const DESCRIPTIONS: Record<StepType, string> = {
  connection_request: "Invites the person to connect, with an optional note.",
  message: "A normal LinkedIn message to someone you are connected to.",
  follow_up: "A later message, sent only if they have not replied.",
  voice_note: "A short voice message to a connection.",
  inmail: "A paid LinkedIn message to someone you are not connected to.",
  free_inmail: "A free message, only for people with an open profile.",
  profile_visit: "Opens their profile so they see you looked.",
  follow: "Follows their profile.",
  like_post: "Likes their most recent post.",
  withdraw_invite: "Takes back an invitation that is still waiting.",
  wait: "Pauses before the next step.",
  if_connected: "Splits the path: connected, or not connected after waiting.",
  if_active: "Splits the path by whether they were recently active.",
  end: "Stops the sequence.",
};

/** Which node types can be added, grouped as the menu shows them. */
export const MENU: { group: string; types: StepType[] }[] = [
  { group: "Messages", types: ["connection_request", "message", "follow_up", "voice_note", "inmail", "free_inmail"] },
  { group: "Profile actions", types: ["profile_visit", "follow", "like_post", "withdraw_invite"] },
  { group: "Timing and conditions", types: ["wait", "if_connected", "if_active"] },
];

export const listOf = (steps: BuilderStep[], parentKey: number | null, branch: Branch | null) =>
  steps.filter((s) => s.parentKey === parentKey && (parentKey === null ? s.branch === null : s.branch === branch));

/** A list that ends in an If step is closed: what comes next lives in the If step's branches. */
export const isClosed = (list: BuilderStep[]) => list.length > 0 && isConditional(list[list.length - 1].type);

export const descendants = (steps: BuilderStep[], key: number): number[] => {
  const out: number[] = [];
  const walk = (k: number) => steps.filter((s) => s.parentKey === k).forEach((s) => { out.push(s.key); walk(s.key); });
  walk(key);
  return out;
};

export const removeNode = (steps: BuilderStep[], key: number): BuilderStep[] => {
  const gone = new Set([key, ...descendants(steps, key)]);
  return steps.filter((s) => !gone.has(s.key));
};

/** A voice note goes to a connection: it is fine in the Connected branch, after a message in the same list, or when everyone is already a connection. */
function voiceFits(steps: BuilderStep[], parentKey: number | null, branch: Branch | null, before: BuilderStep | null, audienceConnections: boolean): boolean {
  if (audienceConnections) return true;
  const parent = parentKey === null ? undefined : steps.find((s) => s.key === parentKey);
  if (parent?.type === "if_connected" && branch === "yes") return true;
  const list = listOf(steps, parentKey, branch);
  const upTo = before ? list.slice(0, list.findIndex((s) => s.key === before.key)) : list;
  return upTo.some((s) => s.type === "message");
}

/** When everyone is already a connection, steps that exist to get connected make no sense. Why a node does not fit that audience, or null. */
export function connectionsOnlyProblem(type: StepType): string | null {
  switch (type) {
    case "connection_request": return "These people are already your connections. Start with a message instead.";
    case "if_connected": return "These people are already connected, so there is nothing to wait for.";
    case "withdraw_invite": return "There is no pending invitation: these people are already your connections.";
    case "inmail":
    case "free_inmail": return "These people are your connections, so send a normal message. InMail is for people you are not connected to.";
    default: return null;
  }
}

/** Why this node cannot be added where it is being added, or null. Mirrors what the server and engine accept. */
export function addProblem(steps: BuilderStep[], type: StepType, parentKey: number | null, branch: Branch | null, audienceConnections = false): string | null {
  const list = listOf(steps, parentKey, branch);
  if (isClosed(list)) return "This branch already ends in a condition. Add steps inside its branches.";
  if (audienceConnections) { const why = connectionsOnlyProblem(type); if (why) return why; }
  if (type === "connection_request" && steps.some((s) => s.type === "connection_request")) return "A sequence has one connection request.";
  if (type === "voice_note" && !voiceFits(steps, parentKey, branch, null, audienceConnections)) return "A voice note goes to a connection. Add it in the Connected branch, or after a message.";
  return null;
}

/** Add a node at the end of a list. A connection request brings its If connection step with it, so both outcomes are visible at once. */
export function addNode(steps: BuilderStep[], type: StepType, parentKey: number | null, branch: Branch | null): BuilderStep[] {
  const made = [newStep(type, parentKey, branch)];
  if (type === "connection_request") made.push(newStep("if_connected", parentKey, branch));
  const list = listOf(steps, parentKey, branch);
  const last = list[list.length - 1];
  const at = last ? steps.findIndex((s) => s.key === last.key) + 1 : steps.length;
  return [...steps.slice(0, at), ...made, ...steps.slice(at)];
}

export interface NodeProblem { key: number; message: string }

/** Everything that stops the Smart sequence from being ready, one entry per node. The same rules the launch check applies on the server. */
export function problems(steps: BuilderStep[], audienceConnections = false): NodeProblem[] {
  const out: NodeProblem[] = [];
  for (const s of steps) {
    const ai = s.aiConfig?.mode === "ai";
    const text = (label: string) => (!s.message.trim() && !ai ? `${label}: write the message.` : null);
    let message: string | null = null;
    const misfit = audienceConnections ? connectionsOnlyProblem(s.type) : null;
    if (misfit) message = `${LABELS[s.type]}: ${misfit.charAt(0).toLowerCase()}${misfit.slice(1)} Remove this step.`;
    else if (s.type === "connection_request" || s.type === "message" || s.type === "follow_up") message = s.type === "connection_request" ? null : text(LABELS[s.type]);
    else if (s.type === "inmail" || s.type === "free_inmail") message = text(LABELS[s.type]);
    else if (s.type === "voice_note") {
      const mode = (s.config.mode as string) ?? "direct";
      if (!voiceFits(steps, s.parentKey, s.branch, s, audienceConnections)) message = "Send voice note: it must follow a message or sit in the Connected branch.";
      else if (mode === "ai" && !String(s.config.script ?? "").trim()) message = "Send voice note: write the script.";
      else if (!s.config.audioId) message = mode === "ai" ? "Send voice note: make the audio from the script." : "Send voice note: record or upload the audio.";
    }
    if (message) out.push({ key: s.key, message });
  }
  return out;
}

/** A plain-words outline of a sequence, indented per branch, for previews. */
export function outline(steps: BuilderStep[]): string[] {
  const lines: string[] = [];
  const walk = (parent: number | null, branch: Branch | null, depth: number) => {
    for (const s of listOf(steps, parent, branch)) {
      const detail = s.type === "wait" ? ` ${s.delayHours >= 24 && s.delayHours % 24 === 0 ? `${s.delayHours / 24} days` : `${s.delayHours} hours`}` : s.type === "if_connected" ? ` (waits up to ${s.config.waitDays ?? 15} days)` : s.type === "if_active" ? ` (last ${s.config.days ?? 30} days)` : "";
      lines.push(`${"  ".repeat(depth)}${LABELS[s.type]}${detail}`);
      if (isConditional(s.type)) {
        lines.push(`${"  ".repeat(depth + 1)}${s.type === "if_connected" ? "Connected" : "Active"}:`);
        walk(s.key, "yes", depth + 2);
        lines.push(`${"  ".repeat(depth + 1)}${s.type === "if_connected" ? "Not connected" : "Not active"}:`);
        walk(s.key, "no", depth + 2);
      }
    }
  };
  walk(null, null, 0);
  return lines;
}
