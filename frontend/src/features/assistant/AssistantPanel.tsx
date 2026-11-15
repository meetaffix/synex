import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, Loader2, Mic, MicOff, Send, Sparkles, Volume2, VolumeX, WifiOff, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useAssistant, type ChatItem } from "./AssistantProvider";

const SUGGESTIONS = ["Summarise my dashboard", "Why is a campaign paused?", "Suggest safe limits for a new account", "Plan a campaign to book demos with fintech CTOs"];

function ProposalCard({ item }: { item: Extract<ChatItem, { kind: "proposal" }> }) {
  const { confirmProposal, cancelProposal } = useAssistant();
  const { proposal, busy, error } = item;
  const done = proposal.status !== "pending";
  return (
    <section aria-label="Proposed change" className="rounded-lg border border-border-strong bg-surface p-4" data-testid="proposal-card">
      <p className="text-xs font-medium text-muted-foreground">Review this change</p>
      <p className="mt-1 text-sm font-medium">{proposal.summary}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {proposal.changes.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
      {done ? (
        <p className="mt-3">
          <Badge variant={proposal.status === "applied" ? "success" : proposal.status === "cancelled" ? "muted" : "danger"}>
            {proposal.status === "applied" ? "Done" : proposal.status === "cancelled" ? "Cancelled" : proposal.status === "expired" ? "Expired" : "Not applied"}
          </Badge>
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" loading={busy} onClick={() => void confirmProposal(item.id)}>
            Confirm
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => void cancelProposal(item.id)}>
            Cancel
          </Button>
        </div>
      )}
      {!done && <p className="mt-2 text-xs text-muted-foreground">Nothing changes until you press Confirm.</p>}
    </section>
  );
}

function DraftCard({ item }: { item: Extract<ChatItem, { kind: "draft" }> }) {
  const { insertDraft, fieldLabel } = useAssistant();
  const [message, setMessage] = useState<string | null>(null);
  return (
    <section aria-label="Draft" className="rounded-lg border border-border bg-surface-muted p-4" data-testid="draft-card">
      <p className="text-xs font-medium text-muted-foreground">Draft {item.label}. It is not sent.</p>
      <p className="mt-2 whitespace-pre-wrap text-sm">{item.text}</p>
      {item.warnings.map((w) => (
        <p key={w} className="mt-2 text-xs text-warning">
          {w}
        </p>
      ))}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setMessage(insertDraft(item.id) ? null : "Click the text field you want to fill, then press Insert again.")}
        >
          {item.inserted ? <Check /> : null}
          {item.inserted ? "Inserted" : fieldLabel ? `Insert into ${fieldLabel}` : "Insert into field"}
        </Button>
      </div>
      {item.inserted && <p className="mt-2 text-xs text-muted-foreground">Inserted. Edit it before you use it.</p>}
      {message && (
        <p role="status" className="mt-2 text-xs text-muted-foreground">
          {message}
        </p>
      )}
    </section>
  );
}

function Message({ item }: { item: ChatItem }) {
  switch (item.kind) {
    case "user":
      return (
        <div className="flex justify-end">
          <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary-soft px-3 py-2 text-sm text-primary-soft-foreground">
            <span className="sr-only">You said: </span>
            {item.text}
          </p>
        </div>
      );
    case "assistant":
      return (
        <div className="flex justify-start">
          <p className="max-w-[90%] whitespace-pre-wrap rounded-lg bg-surface-muted px-3 py-2 text-sm">
            <span className="sr-only">Assistant: </span>
            {item.text}
          </p>
        </div>
      );
    case "proposal":
      return <ProposalCard item={item} />;
    case "draft":
      return <DraftCard item={item} />;
    case "notice":
      return (
        <p role={item.tone === "danger" ? "alert" : "status"} className={cn("flex items-start gap-2 rounded-md px-3 py-2 text-sm", item.tone === "danger" ? "bg-danger-soft text-danger" : "bg-surface-muted text-muted-foreground")}>
          {item.tone === "danger" && <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />}
          <span>{item.text}</span>
        </p>
      );
  }
}

function StatusPill() {
  const { phase, recording, userSpeaking, thinking, working, agentSpeaking, online } = useAssistant();
  let label = "Ready";
  let variant: "success" | "warning" | "danger" | "muted" | "info" = "muted";
  if (!online) [label, variant] = ["Offline", "danger"];
  else if (recording && userSpeaking) [label, variant] = ["Listening", "danger"];
  else if (recording) [label, variant] = ["Recording", "danger"];
  else if (working) [label, variant] = ["Working", "info"];
  else if (thinking) [label, variant] = ["Thinking", "info"];
  else if (agentSpeaking) [label, variant] = ["Speaking", "success"];
  else if (phase === "connecting") [label, variant] = ["Connecting", "warning"];
  else if (phase === "live") [label, variant] = ["Connected", "success"];
  return (
    <Badge variant={variant} data-testid="assistant-status" aria-live="polite">
      <span aria-hidden className={cn("size-2 rounded-full bg-current", recording && "animate-pulse motion-reduce:animate-none")} />
      {label}
    </Badge>
  );
}

function BlockedState() {
  const { blocked, settings } = useAssistant();
  if (!blocked && !(settings && (!settings.enabled || !settings.available || settings.capReached))) return null;
  let title = "The assistant is unavailable";
  let text = blocked?.message ?? "";
  if (blocked?.code === "cap_reached" || settings?.capReached) {
    title = "Monthly assistant minutes used up";
    text = `This workspace has used its ${settings?.monthlyMinuteCap ?? ""} assistant minutes for the month. An admin can raise the cap in Settings, or it resets next month.`;
  } else if (blocked?.code === "disabled" || settings?.enabled === false) {
    title = "The assistant is turned off";
    text = "An admin turned it off for this workspace. They can turn it back on in Settings.";
  } else if (blocked?.code === "unavailable" || settings?.available === false) {
    title = "The assistant isn't set up yet";
    text = "Whoever runs Synex needs to add the voice service key to the server.";
  }
  return (
    <div role="alert" data-testid="assistant-blocked" className="m-4 rounded-lg border border-border bg-surface-muted p-4">
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{text}</p>
      <Button asChild variant="secondary" size="sm" className="mt-3">
        <Link to="/settings">Open Settings</Link>
      </Button>
    </div>
  );
}

export function AssistantPanel() {
  const a = useAssistant();
  const { open, items, thinking, working, panelRef, settings, settingsLoading, settingsError, blocked, online } = a;
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const locked = !!blocked || (!!settings && (!settings.enabled || !settings.available || settings.capReached));

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [items.length, thinking]);

  if (!open) return null;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const value = text;
    if (!value.trim() || locked) return;
    setText("");
    void a.sendText(value);
  };
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      a.setOpen(false);
      document.getElementById("assistant-button")?.focus();
    }
  };
  const micLabel = a.voiceMode === "push" ? "Hold to talk" : a.recording ? "Stop listening" : "Start listening";

  return (
    <aside
      ref={panelRef}
      aria-label="Assistant"
      onKeyDown={onKey}
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-border bg-surface text-foreground shadow-float animate-rise motion-reduce:animate-none sm:w-[420px]"
    >
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Sparkles className="size-4 text-primary" aria-hidden />
        <h2 className="text-base font-semibold">Assistant</h2>
        <StatusPill />
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" onClick={a.toggleMute} aria-pressed={a.speakerMuted} aria-label={a.speakerMuted ? "Unmute spoken replies" : "Mute spoken replies"}>
            {a.speakerMuted ? <VolumeX /> : <Volume2 />}
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => a.setOpen(false)} aria-label="Close assistant">
            <X />
          </Button>
        </div>
      </header>
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" data-testid="assistant-disclosure">
        Voice and workspace data are processed by Deepgram and the language model it uses. Synex stores no audio.{" "}
        <Link to="/privacy" className="text-primary underline underline-offset-2">
          Privacy
        </Link>
      </p>

      {!online && (
        <p role="alert" className="flex items-center gap-2 bg-danger-soft px-4 py-2 text-sm text-danger" data-testid="assistant-offline">
          <WifiOff className="size-4" aria-hidden /> You are offline. The assistant needs a connection.
        </p>
      )}

      <div ref={log} role="log" aria-live="polite" aria-label="Conversation" className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {settingsLoading && (
          <div className="space-y-2" aria-label="Loading the assistant">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-8 w-1/2" />
          </div>
        )}
        {settingsError && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
            The assistant could not load. Check your connection and try again.
          </p>
        )}
        {!settingsLoading && !locked && items.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Ask about your campaigns, leads and accounts, or have it plan and draft. It prepares changes and waits for you to confirm. Type below or use the microphone.</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <Button key={s} variant="secondary" size="sm" onClick={() => void a.sendText(s)}>
                  {s}
                </Button>
              ))}
            </div>
          </div>
        )}
        {items.map((item) => (
          <Message key={item.id} item={item} />
        ))}
        {(thinking || working) && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="assistant-thinking">
            <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
            {working ? `Working: ${working}` : "Thinking"}
          </p>
        )}
      </div>

      <BlockedState />

      <div className="border-t border-border p-4">
        {a.micState === "explain" && (
          <div role="group" aria-label="Microphone access" className="mb-3 rounded-lg border border-border bg-surface-muted p-3" data-testid="mic-explain">
            <p className="text-sm font-medium">Use your microphone?</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Your browser will ask for permission. Audio is sent to Deepgram only while you are recording, you will see a red Recording label, and Synex stores no audio.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={a.allowMic}>
                Continue
              </Button>
              <Button size="sm" variant="secondary" onClick={a.dismissMicExplain}>
                Not now
              </Button>
            </div>
          </div>
        )}
        {a.micState === "denied" && (
          <p role="alert" className="mb-3 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning" data-testid="mic-denied">
            The microphone is blocked, so voice is off. You can keep typing, or allow the microphone for this site in your browser settings and press the mic again.
          </p>
        )}
        {a.voiceUnavailable && (
          <p className="mb-3 text-xs text-muted-foreground" data-testid="voice-unavailable">
            Voice isn't available here: {a.voiceUnavailable} Typing works fully.
          </p>
        )}
        {a.recording && (
          <p role="status" className="mb-3 flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-sm font-medium text-danger" data-testid="recording-indicator">
            <span aria-hidden className="size-2 animate-pulse rounded-full bg-danger motion-reduce:animate-none" />
            Recording{a.voiceMode === "push" ? ". Release to stop." : ". Hands-free: press the mic to stop."}
          </p>
        )}

        <form onSubmit={submit} className="flex items-end gap-2">
          <label htmlFor="assistant-input" className="sr-only">
            Message the assistant
          </label>
          <textarea
            id="assistant-input"
            ref={input}
            value={text}
            rows={2}
            disabled={locked}
            placeholder={locked ? "The assistant is unavailable" : "Type a message"}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            className="min-h-10 flex-1 resize-none rounded-sm border border-input bg-surface px-3 py-2 text-sm placeholder:text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:bg-surface-muted"
          />
          <Button
            type="button"
            variant={a.recording ? "danger" : "secondary"}
            size="icon"
            aria-label={micLabel}
            aria-pressed={a.recording}
            disabled={locked || !!a.voiceUnavailable || a.micState === "requesting"}
            data-testid="mic-button"
            onPointerDown={(e) => {
              if (a.voiceMode === "push") {
                e.preventDefault();
                a.pressMic();
              }
            }}
            onPointerUp={() => a.releaseMic()}
            onPointerLeave={() => a.releaseMic()}
            onKeyDown={(e) => {
              if (a.voiceMode === "push" && (e.key === " " || e.key === "Enter") && !e.repeat) {
                e.preventDefault();
                a.pressMic();
              }
            }}
            onKeyUp={(e) => {
              if (a.voiceMode === "push" && (e.key === " " || e.key === "Enter")) a.releaseMic();
            }}
            onClick={() => {
              if (a.voiceMode === "hands-free") a.pressMic();
            }}
          >
            {a.micState === "denied" ? <MicOff /> : <Mic />}
          </Button>
          <Button type="submit" size="icon" aria-label="Send message" disabled={locked || !text.trim() || !online}>
            <Send />
          </Button>
        </form>

        <fieldset className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <legend className="sr-only">Voice mode</legend>
          {(["push", "hands-free"] as const).map((mode) => (
            <label key={mode} className="flex cursor-pointer items-center gap-2">
              <input type="radio" name="voice-mode" checked={a.voiceMode === mode} onChange={() => a.setVoiceMode(mode)} className="accent-[rgb(var(--primary))]" />
              {mode === "push" ? "Push to talk" : "Hands-free"}
            </label>
          ))}
          {a.fieldLabel && <span className="ml-auto truncate" title={a.fieldLabel}>Field: {a.fieldLabel}</span>}
        </fieldset>
      </div>
    </aside>
  );
}
