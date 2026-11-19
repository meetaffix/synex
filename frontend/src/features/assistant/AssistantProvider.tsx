import { startRecording as startWav, toBase64 } from "@/lib/recorder";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, config } from "@/services/client";
import { MicCapture, Player, voiceSupport } from "./audio";
import { assistantService, type AssistantSettings, type PageContext, type Proposal } from "./service";

export type Phase = "idle" | "connecting" | "live" | "ended";
export type MicState = "off" | "explain" | "requesting" | "on" | "denied";
export type VoiceMode = "push" | "hands-free";

export type ChatItem =
  | { id: string; kind: "user"; text: string }
  | { id: string; kind: "assistant"; text: string }
  | { id: string; kind: "proposal"; proposal: Proposal; busy?: boolean; error?: string }
  | { id: string; kind: "draft"; text: string; label: string; warnings: string[]; inserted?: boolean }
  | { id: string; kind: "notice"; tone: "info" | "danger"; text: string };

interface AssistantValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  items: ChatItem[];
  phase: Phase;
  thinking: boolean;
  working: string | null;
  agentSpeaking: boolean;
  userSpeaking: boolean;
  micState: MicState;
  recording: boolean;
  voiceMode: VoiceMode;
  setVoiceMode: (mode: VoiceMode) => void;
  voiceUnavailable: string | null;
  speakerMuted: boolean;
  toggleMute: () => void;
  online: boolean;
  settings: AssistantSettings | undefined;
  settingsLoading: boolean;
  settingsError: boolean;
  blocked: { code: "disabled" | "cap_reached" | "unavailable"; message: string } | null;
  sendText: (text: string) => Promise<void>;
  pressMic: () => void;
  releaseMic: () => void;
  allowMic: () => void;
  dismissMicExplain: () => void;
  confirmProposal: (itemId: string) => Promise<void>;
  cancelProposal: (itemId: string) => Promise<void>;
  insertDraft: (itemId: string) => boolean;
  fieldLabel: string | null;
  setPageContext: (ctx: { campaignId?: string; leadId?: string } | null) => void;
  endSession: () => void;
  panelRef: React.RefObject<HTMLElement | null>;
}

const Ctx = createContext<AssistantValue | null>(null);

export function useAssistant(): AssistantValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useAssistant must be used inside AssistantProvider");
  return value;
}

const MIC_EXPLAINED = "synex.assistant.mic-explained";
const VOICE_MODE = "synex.assistant.voice-mode";
const MUTED = "synex.assistant.muted";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* a convenience only */
  }
}

let counter = 0;
const nextId = () => `a${++counter}`;

function fieldLabelOf(el: HTMLElement): string {
  const aria = el.getAttribute("aria-label");
  if (aria) return aria;
  const labelled = el.getAttribute("aria-labelledby");
  if (labelled) {
    const text = document.getElementById(labelled)?.textContent;
    if (text) return text.trim();
  }
  if (el.id) {
    const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (label?.textContent) return label.textContent.replace(/\(optional\)/i, "").trim();
  }
  return (el as HTMLInputElement).placeholder || "a text field";
}

function isTextField(el: EventTarget | null): el is HTMLInputElement | HTMLTextAreaElement {
  if (el instanceof HTMLTextAreaElement) return !el.readOnly && !el.disabled;
  if (el instanceof HTMLInputElement) return ["text", "search", "email", "url", ""].includes(el.type) && !el.readOnly && !el.disabled;
  return false;
}

export function AssistantProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { pathname, search } = useLocation();
  const [open, setOpenState] = useState(false);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [thinking, setThinking] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [micState, setMicState] = useState<MicState>("off");
  const [voiceMode, setVoiceModeState] = useState<VoiceMode>(() => (read(VOICE_MODE) === "hands-free" ? "hands-free" : "push"));
  const [speakerMuted, setSpeakerMuted] = useState(() => read(MUTED) === "1");
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [blocked, setBlocked] = useState<AssistantValue["blocked"]>(null);
  const [fieldLabel, setFieldLabel] = useState<string | null>(null);
  const [registered, setRegistered] = useState<{ campaignId?: string; leadId?: string } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const liveRef = useRef(false);
  const sessionMode = useRef<"voice" | "text" | null>(null);
  const readyWaiters = useRef<{ resolve: () => void; reject: (e: Error) => void } | null>(null);
  const connecting = useRef<Promise<void> | null>(null);
  const player = useRef<Player | null>(null);
  const mic = useRef<MicCapture | null>(null);
  const fieldRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const speakingTimer = useRef<number | undefined>(undefined);
  const voiceModeRef = useRef(voiceMode);
  voiceModeRef.current = voiceMode;

  player.current ??= new Player();
  mic.current ??= new MicCapture();
  player.current.muted = speakerMuted;
  player.current.onSpeaking = setAgentSpeaking;

  const support = useMemo(() => voiceSupport(), []);
  const voiceUnavailable = support.ok ? null : support.reason;

  const settingsQuery = useQuery({ queryKey: ["assistant", "settings"], queryFn: assistantService.settings, enabled: open, staleTime: 5_000 });
  // When the workspace chose local models the panel talks to the local endpoints instead of opening a Deepgram session.
  const localMode = settingsQuery.data?.provider === "local";
  const providersQuery = useQuery({ queryKey: ["assistant", "providers"], queryFn: assistantService.providers, enabled: open && localMode, staleTime: 15_000 });
  const localParts = useMemo(() => Object.fromEntries((providersQuery.data?.providers.find((p) => p.id === "local")?.parts ?? []).map((p) => [p.id, p.ready])) as Record<string, boolean>, [providersQuery.data]);
  const wavRecorder = useRef<{ stop: () => Promise<File> } | null>(null);
  const mutedRef = useRef(speakerMuted);
  mutedRef.current = speakerMuted;

  // ---- what the user is looking at -------------------------------------------------------------------------
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const pageContext = useMemo<PageContext>(
    () => ({
      path: pathname,
      campaignId: registered?.campaignId ?? params.get("campaignId") ?? undefined,
      leadId: registered?.leadId ?? params.get("leadId") ?? undefined,
      field: fieldLabel ?? undefined,
    }),
    [pathname, params, registered, fieldLabel],
  );
  const pageRef = useRef(pageContext);
  pageRef.current = pageContext;
  const contextKey = JSON.stringify(pageContext);
  useEffect(() => {
    if (!liveRef.current) return;
    const timer = window.setTimeout(() => wsRef.current?.send(JSON.stringify({ type: "context", page: pageRef.current })), 300);
    return () => window.clearTimeout(timer);
  }, [contextKey]);

  useEffect(() => {
    const onFocus = (event: FocusEvent) => {
      if (!isTextField(event.target) || panelRef.current?.contains(event.target)) return;
      fieldRef.current = event.target;
      setFieldLabel(fieldLabelOf(event.target));
    };
    document.addEventListener("focusin", onFocus);
    return () => document.removeEventListener("focusin", onFocus);
  }, []);

  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);

  // ---- helpers ---------------------------------------------------------------------------------------------
  const push = useCallback((item: ChatItem) => setItems((current) => [...current, item]), []);
  const notice = useCallback((text: string, tone: "info" | "danger" = "info") => push({ id: nextId(), kind: "notice", tone, text }), [push]);

  const stopMic = useCallback(() => {
    mic.current?.stop();
    setMicState((state) => (state === "denied" ? state : "off"));
  }, []);

  const teardown = useCallback(
    (nextPhase: Phase) => {
      liveRef.current = false;
      const ws = wsRef.current;
      wsRef.current = null;
      sessionMode.current = null;
      if (ws) {
        ws.onmessage = ws.onclose = ws.onerror = null;
        try {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "end" }));
          ws.close();
        } catch {
          /* already closed */
        }
      }
      readyWaiters.current?.reject(new Error("closed"));
      readyWaiters.current = null;
      connecting.current = null;
      stopMic();
      player.current?.flush();
      setThinking(false);
      setWorking(null);
      setUserSpeaking(false);
      setPhase(nextPhase);
    },
    [stopMic],
  );

  const onMessage = useCallback(
    (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        player.current?.push(event.data);
        return;
      }
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(String(event.data));
      } catch {
        return;
      }
      switch (msg.type) {
        case "ready":
          liveRef.current = true;
          setPhase("live");
          readyWaiters.current?.resolve();
          readyWaiters.current = null;
          break;
        case "transcript": {
          const text = String(msg.text ?? "");
          if (!text) break;
          if (msg.role === "user") {
            setItems((current) => [...current, { id: nextId(), kind: "user", text }]);
            setThinking(true);
          } else {
            setThinking(false);
            setItems((current) => {
              const last = current[current.length - 1];
              if (last?.kind === "assistant") return [...current.slice(0, -1), { ...last, text: `${last.text} ${text}` }];
              return [...current, { id: nextId(), kind: "assistant", text }];
            });
          }
          break;
        }
        case "user_speaking":
          player.current?.flush();
          setUserSpeaking(true);
          window.clearTimeout(speakingTimer.current);
          speakingTimer.current = window.setTimeout(() => setUserSpeaking(false), 1500);
          break;
        case "thinking":
          setThinking(true);
          break;
        case "agent_audio_done":
          setThinking(false);
          break;
        case "tool":
          setWorking(msg.status === "running" ? String(msg.name ?? "").replace(/_/g, " ") : null);
          break;
        case "proposal":
          setThinking(false);
          push({ id: nextId(), kind: "proposal", proposal: msg.proposal as Proposal });
          break;
        case "draft":
          setThinking(false);
          push({ id: nextId(), kind: "draft", text: String(msg.text ?? ""), label: String(msg.label ?? "message"), warnings: (msg.warnings as string[]) ?? [] });
          break;
        case "error": {
          const code = String(msg.code);
          const text = String(msg.message ?? "Something went wrong.");
          if (code === "cap_reached" || code === "disabled") setBlocked({ code, message: text });
          notice(text, "danger");
          setThinking(false);
          break;
        }
        case "closed": {
          const reason = String(msg.reason);
          const idle = settingsQuery.data?.idleTimeoutSeconds;
          if (reason === "idle") notice(`The session ended after ${idle ? Math.round(idle / 60) || 1 : 2} minutes with no activity. Send a message to start again.`);
          else if (reason === "cap_reached") {
            setBlocked({ code: "cap_reached", message: "This workspace has used its assistant minutes for the month." });
            notice("The session ended: this workspace has used its assistant minutes for the month.", "danger");
          }
          void queryClient.invalidateQueries({ queryKey: ["assistant", "settings"] });
          teardown("ended");
          break;
        }
      }
    },
    [notice, push, queryClient, settingsQuery.data?.idleTimeoutSeconds, teardown],
  );

  // ---- connection ------------------------------------------------------------------------------------------
  const connect = useCallback(
    async (mode: "voice" | "text"): Promise<void> => {
      if (liveRef.current && sessionMode.current === mode) return;
      if (connecting.current && sessionMode.current === mode) return connecting.current;
      if (wsRef.current) teardown("idle");
      setBlocked(null);
      setPhase("connecting");
      sessionMode.current = mode;
      const attempt = (async () => {
        let info;
        try {
          info = await assistantService.startSession(mode, pageRef.current);
        } catch (error) {
          const message = error instanceof ApiError ? error.message : "Could not start the assistant.";
          if (error instanceof ApiError && error.status === 429) setBlocked({ code: "cap_reached", message });
          else if (error instanceof ApiError && error.status === 403) setBlocked({ code: "disabled", message });
          else if (error instanceof ApiError && error.status === 503) setBlocked({ code: "unavailable", message });
          else notice(message, "danger");
          teardown("idle");
          throw error;
        }
        await new Promise<void>((resolve, reject) => {
          readyWaiters.current = { resolve, reject };
          const ws = new WebSocket(`${config.API_URL.replace(/^http/, "ws")}${info.wsPath}`);
          ws.binaryType = "arraybuffer";
          wsRef.current = ws;
          ws.onopen = () => ws.send(JSON.stringify({ type: "auth", ticket: info.ticket }));
          ws.onmessage = onMessage;
          ws.onerror = () => undefined;
          ws.onclose = () => {
            if (wsRef.current !== ws) return;
            const wasLive = liveRef.current;
            notice(wasLive ? "The connection dropped. Send a message to reconnect." : "Could not reach the assistant. Check your connection and try again.", "danger");
            teardown("ended");
            reject(new Error("closed"));
          };
        });
      })();
      connecting.current = attempt;
      try {
        await attempt;
      } finally {
        if (connecting.current === attempt) connecting.current = null;
      }
    },
    [notice, onMessage, teardown],
  );

  const endSession = useCallback(() => teardown("idle"), [teardown]);

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next);
      if (!next) teardown("idle");
    },
    [teardown],
  );
  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "j") {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  useEffect(
    () => () => {
      // Leaving the app shell (sign-out, route out) ends the session and releases the microphone.
      teardown("idle");
      player.current?.close();
    },
    [teardown],
  );

  // ---- local models (Ollama, Whisper, Piper) ----------------------------------------------------------------
  const speakReply = useCallback(async (text: string) => {
    if (mutedRef.current || !localParts.tts) return;
    try {
      const url = URL.createObjectURL(await assistantService.speak(text));
      const audio = new Audio(url);
      setAgentSpeaking(true);
      audio.onended = audio.onerror = () => { setAgentSpeaking(false); URL.revokeObjectURL(url); };
      await audio.play();
    } catch {
      setAgentSpeaking(false);
    }
  }, [localParts.tts]);

  const sendLocal = useCallback(async (text: string) => {
    const history = itemsRef.current.flatMap((i) => (i.kind === "user" ? [{ role: "user", content: i.text }] : i.kind === "assistant" ? [{ role: "assistant", content: i.text }] : []));
    push({ id: nextId(), kind: "user", text });
    setThinking(true);
    try {
      const reply = await assistantService.localChat(text, history, pageRef.current);
      push({ id: nextId(), kind: "assistant", text: reply.reply });
      for (const card of reply.cards) {
        if (card.type === "proposal" && card.proposal) push({ id: nextId(), kind: "proposal", proposal: card.proposal });
        else if (card.type === "draft") push({ id: nextId(), kind: "draft", text: String(card.text ?? ""), label: String(card.label ?? "message"), warnings: card.warnings ?? [] });
      }
      void speakReply(reply.reply);
    } catch (error) {
      notice(error instanceof ApiError ? error.message : "The local assistant could not answer.", "danger");
    } finally {
      setThinking(false);
    }
  }, [notice, push, speakReply]);

  const toggleLocalMic = useCallback(async () => {
    if (wavRecorder.current) {
      const handle = wavRecorder.current;
      wavRecorder.current = null;
      setMicState("off");
      try {
        const file = await handle.stop();
        const heard = await assistantService.transcribe(toBase64(await file.arrayBuffer()));
        await sendLocal(heard.text);
      } catch (error) {
        notice(error instanceof ApiError ? error.message : "The recording could not be used. You can keep typing.", "danger");
      }
      return;
    }
    if (!localParts.stt) {
      notice("Speech to text (Whisper) is not set up on this computer, so the microphone cannot be used. Type instead, or see Settings, Assistant.", "info");
      return;
    }
    setMicState("requesting");
    try {
      wavRecorder.current = await startWav();
      setMicState("on");
    } catch (error) {
      const denied = error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError");
      setMicState(denied ? "denied" : "off");
      if (!denied) notice("The microphone could not be started. You can keep typing.", "danger");
    }
  }, [localParts.stt, notice, sendLocal]);

  // ---- typing ----------------------------------------------------------------------------------------------
  const sendText = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      if (!navigator.onLine) {
        notice("You are offline. Reconnect to use the assistant.", "danger");
        return;
      }
      if (localMode) return sendLocal(text);
      try {
        await connect(sessionMode.current ?? (mic.current?.active ? "voice" : "text"));
      } catch {
        return;
      }
      wsRef.current?.send(JSON.stringify({ type: "user_text", text }));
      setThinking(true);
    },
    [connect, localMode, notice, sendLocal],
  );

  // ---- voice -----------------------------------------------------------------------------------------------
  const startRecording = useCallback(async () => {
    if (!support.ok) return;
    if (!navigator.onLine) {
      notice("You are offline. Reconnect to use the assistant.", "danger");
      return;
    }
    player.current?.flush();
    setMicState("requesting");
    try {
      await mic.current!.start((pcm) => {
        if (liveRef.current && wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(pcm);
      });
    } catch (error) {
      const denied = error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError");
      setMicState(denied ? "denied" : "off");
      if (!denied) notice("The microphone could not be started. You can keep typing.", "danger");
      return;
    }
    setMicState("on");
    try {
      await connect("voice");
      wsRef.current?.send(JSON.stringify({ type: "activity" }));
    } catch {
      stopMic();
    }
  }, [connect, notice, stopMic, support.ok]);

  const pressMic = useCallback(() => {
    if (localMode) { void toggleLocalMic(); return; }
    if (!support.ok) return;
    if (micState === "on" || micState === "requesting") {
      if (voiceModeRef.current === "hands-free") stopMic();
      return;
    }
    if (read(MIC_EXPLAINED) !== "1") {
      setMicState("explain");
      return;
    }
    void startRecording();
  }, [localMode, micState, startRecording, stopMic, support.ok, toggleLocalMic]);

  const releaseMic = useCallback(() => {
    if (localMode) return;
    if (voiceModeRef.current === "push" && mic.current?.active) stopMic();
  }, [localMode, stopMic]);

  const allowMic = useCallback(() => {
    write(MIC_EXPLAINED, "1");
    void startRecording();
  }, [startRecording]);

  const dismissMicExplain = useCallback(() => setMicState("off"), []);

  const setVoiceMode = useCallback(
    (mode: VoiceMode) => {
      write(VOICE_MODE, mode);
      setVoiceModeState(mode);
      stopMic();
    },
    [stopMic],
  );

  const toggleMute = useCallback(() => {
    setSpeakerMuted((current) => {
      const next = !current;
      write(MUTED, next ? "1" : "0");
      if (next) player.current?.flush();
      return next;
    });
  }, []);

  // ---- confirmation cards and drafts ----------------------------------------------------------------------
  const patchItem = useCallback((id: string, patch: Partial<Extract<ChatItem, { kind: "proposal" }>>) => {
    setItems((current) => current.map((item) => (item.id === id && item.kind === "proposal" ? { ...item, ...patch } : item)));
  }, []);

  const settle = useCallback(
    async (itemId: string, action: "confirm" | "cancel") => {
      const item = items.find((i) => i.id === itemId);
      if (!item || item.kind !== "proposal" || item.busy || item.proposal.status !== "pending") return;
      patchItem(itemId, { busy: true, error: undefined });
      try {
        const proposal = await (action === "confirm" ? assistantService.confirm(item.proposal.id) : assistantService.cancel(item.proposal.id));
        patchItem(itemId, { busy: false, proposal });
        if (action === "confirm") void queryClient.invalidateQueries();
        if (liveRef.current) wsRef.current?.send(JSON.stringify({ type: "note", proposalId: item.proposal.id }));
      } catch (error) {
        patchItem(itemId, { busy: false, error: error instanceof ApiError ? error.message : "Could not apply this change." });
      }
    },
    [items, patchItem, queryClient],
  );
  const confirmProposal = useCallback((id: string) => settle(id, "confirm"), [settle]);
  const cancelProposal = useCallback((id: string) => settle(id, "cancel"), [settle]);

  const insertDraft = useCallback((itemId: string): boolean => {
    const item = itemsRef.current.find((i) => i.id === itemId);
    const field = fieldRef.current;
    if (!item || item.kind !== "draft" || !field || !field.isConnected) return false;
    const start = field.selectionStart ?? field.value.length;
    const end = field.selectionEnd ?? field.value.length;
    const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(field, field.value.slice(0, start) + item.text + field.value.slice(end));
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.focus();
    setItems((current) => current.map((i) => (i.id === itemId && i.kind === "draft" ? { ...i, inserted: true } : i)));
    return true;
  }, []);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const value: AssistantValue = {
    open,
    setOpen,
    toggle,
    items,
    phase,
    thinking,
    working,
    agentSpeaking,
    userSpeaking,
    micState,
    recording: micState === "on",
    voiceMode,
    setVoiceMode,
    voiceUnavailable: localMode ? (typeof MediaRecorder === "undefined" ? "This browser cannot record audio." : null) : voiceUnavailable,
    speakerMuted,
    toggleMute,
    online,
    settings: settingsQuery.data,
    settingsLoading: settingsQuery.isLoading,
    settingsError: settingsQuery.isError,
    blocked,
    sendText,
    pressMic,
    releaseMic,
    allowMic,
    dismissMicExplain,
    confirmProposal,
    cancelProposal,
    insertDraft,
    fieldLabel,
    setPageContext: setRegistered,
    endSession,
    panelRef,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** A page that shows one campaign or lead calls this so the assistant knows what the user is looking at. */
export function useAssistantPage(ctx: { campaignId?: string; leadId?: string } | null) {
  const { setPageContext } = useAssistant();
  const key = ctx ? `${ctx.campaignId ?? ""}|${ctx.leadId ?? ""}` : "";
  useEffect(() => {
    setPageContext(ctx);
    return () => setPageContext(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, setPageContext]);
}
