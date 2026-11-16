import { useEffect, useRef, useState } from "react";
import { Clock, Paperclip, Mic, Smile, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { UserAvatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { cn } from "@/lib/utils";
import { formatDate } from "@/utils/format";
import { useInboxActions, useScheduled, useSuggestCost, useThread, type InboxItem } from "./model";

const EMOJI = ["🙂", "👍", "🙏", "😊", "🎉", "👋", "🤝", "✅"];

interface Props {
  conversation: InboxItem;
  onBack: () => void;
}

export function ThreadView({ conversation, onBack }: Props) {
  const thread = useThread(conversation.id);
  const scheduled = useScheduled(conversation.id);
  const cost = useSuggestCost();
  const actions = useInboxActions();
  const [text, setText] = useState(conversation.draftBody);
  const [when, setWhen] = useState("");
  const [showSchedule, setShowSchedule] = useState(false);
  const [emoji, setEmoji] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const area = useRef<HTMLTextAreaElement>(null);
  const readOnly = !conversation.accountId;

  useEffect(() => () => window.clearTimeout(timer.current), []);
  const edit = (value: string) => {
    setText(value);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => actions.saveDraft.mutate({ id: conversation.id, body: value }), 1200); // a draft is saved as you type
  };
  const send = () =>
    actions.reply.mutate({ id: conversation.id, body: text.trim() }, {
      onSuccess: () => { setText(""); actions.saveDraft.mutate({ id: conversation.id, body: "" }); toast.success("Reply queued. It sends within your sender's limits."); void thread.refetch(); },
      onError: (error) => toast.error(requestFailureMessage(error)),
    });
  const schedule = () =>
    actions.schedule.mutate({ id: conversation.id, body: text.trim(), sendAt: new Date(when).toISOString() }, {
      onSuccess: () => { setText(""); setWhen(""); setShowSchedule(false); toast.success("Message scheduled."); void scheduled.refetch(); },
      onError: (error) => toast.error(requestFailureMessage(error)),
    });
  const suggest = () =>
    actions.suggest.mutate(conversation.id, { onSuccess: (r) => { setText(r.text); toast.success(`Suggested reply written by ${r.provider}. Review it before sending.`); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const insert = (e: string) => {
    const el = area.current;
    const at = el?.selectionStart ?? text.length;
    edit(text.slice(0, at) + e + text.slice(el?.selectionEnd ?? at));
  };

  const dates = new Set<string>();
  return (
    <div className="flex h-full min-h-[24rem] min-w-0 flex-col">
      <header className="flex items-start gap-3 border-b border-border p-4">
        <Button variant="ghost" size="sm" className="lg:hidden" onClick={onBack}>Back</Button>
        <UserAvatar name={conversation.leadName} className="size-10" />
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold">{conversation.leadName}</h2>
          <p className="truncate text-sm text-muted-foreground">
            {[conversation.leadTitle, conversation.leadCompany].filter(Boolean).join(" at ") || "No title"}
            {conversation.campaignName ? ` · Campaign: ${conversation.campaignName}` : ""}
          </p>
        </div>
        <span className="ml-auto shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-xs">LinkedIn</span>
      </header>
      <div className="flex-1 overflow-y-auto p-4" aria-live="polite">
        {thread.isLoading && <div role="status" aria-label="Loading messages" className="grid gap-3"><Skeleton className="h-12 w-2/3" /><Skeleton className="ml-auto h-12 w-2/3" /></div>}
        {thread.isError && (
          <div role="alert" className="grid justify-items-start gap-2">
            <p className="text-sm text-danger">Messages could not be loaded. {requestFailureMessage(thread.error)}</p>
            <Button size="sm" variant="outline" onClick={() => void thread.refetch()}>Try again</Button>
          </div>
        )}
        {thread.data?.length === 0 && <p className="text-sm text-muted-foreground">There are no messages in this conversation yet.</p>}
        <ol className="grid grid-cols-[minmax(0,1fr)] gap-4">
          {thread.data?.map((message) => {
            const day = formatDate(message.sentAt, "EEEE, MMM d");
            const first = !dates.has(day);
            dates.add(day);
            return (
              <li key={message.id} className="grid gap-2">
                {first && <p className="text-center text-xs text-muted-foreground">{day}</p>}
                <div className={message.direction === "outbound" ? "max-w-full justify-self-end text-right" : "max-w-full justify-self-start"}>
                  <p className="text-xs text-muted-foreground">
                    {message.direction === "outbound" ? "You" : conversation.leadName} · <span className="tabular-nums">{formatDate(message.sentAt, "h:mm a")}</span>
                    {message.deliveryStatus && message.deliveryStatus !== "sent" ? ` · ${message.deliveryStatus === "queued" ? "Queued" : "Not delivered"}` : ""}
                  </p>
                  <p className={cn("mt-1 max-w-prose whitespace-pre-wrap break-words rounded-md px-3 py-2 text-left text-sm", message.direction === "outbound" ? "bg-primary-soft text-primary-soft-foreground" : "border border-border bg-surface")}>{message.body}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
      {(scheduled.data ?? []).filter((s) => s.status !== "cancelled").length > 0 && (
        <ul aria-label="Scheduled messages" className="grid gap-1 border-t border-border bg-surface-muted p-3 text-sm">
          {(scheduled.data ?? []).filter((s) => s.status !== "cancelled").map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2">
              <Clock className="size-4" aria-hidden />
              <span>{s.status === "pending" ? "Scheduled" : s.status === "sent" ? "Sent" : "Not sent"} for {formatDate(s.sendAt, "MMM d, h:mm a")}: {s.body.slice(0, 60)}</span>
              {s.error && <span className="text-danger">{s.error}</span>}
              {s.status === "pending" && <Button size="sm" variant="ghost" onClick={() => actions.cancelScheduled.mutate(s.id, { onSuccess: () => void scheduled.refetch() })}>Cancel</Button>}
            </li>
          ))}
        </ul>
      )}
      <form className="grid gap-2 border-t border-border p-4" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(); }}>
        <label htmlFor="reply" className="text-sm font-medium">Reply</label>
        {readOnly ? (
          <p role="note" className="rounded-lg border border-border bg-surface-muted p-3 text-sm text-muted-foreground">Replies are disabled for this read-only conversation: it has no sender account to send from.</p>
        ) : (
          <>
            <Textarea id="reply" ref={area} rows={3} value={text} onChange={(e) => edit(e.target.value)} placeholder="Write a reply" maxLength={3000} />
            {emoji && <div role="group" aria-label="Emoji" className="flex flex-wrap gap-1">{EMOJI.map((e) => <Button key={e} type="button" size="sm" variant="ghost" aria-label={`Insert ${e}`} onClick={() => insert(e)}>{e}</Button>)}</div>}
            {showSchedule && (
              <div className="flex flex-wrap items-end gap-2">
                <div className="grid gap-1"><label htmlFor="when" className="text-sm font-medium">Send at</label><Input id="when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></div>
                <Button type="button" size="sm" disabled={!text.trim() || !when} loading={actions.schedule.isPending} onClick={schedule}>Schedule message</Button>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="outline" aria-pressed={emoji} onClick={() => setEmoji(!emoji)}><Smile aria-hidden /> Emoji</Button>
              <Button type="button" size="sm" variant="outline" disabled title="Coming soon"><Paperclip aria-hidden /> Attach (coming soon)</Button>
              <Button type="button" size="sm" variant="outline" disabled title="Coming soon"><Mic aria-hidden /> Voice message (coming soon)</Button>
              <Button type="button" size="sm" variant="outline" aria-pressed={showSchedule} onClick={() => setShowSchedule(!showSchedule)}><Clock aria-hidden /> Schedule message</Button>
              <Button type="button" size="sm" variant="outline" loading={actions.suggest.isPending} disabled={!thread.data?.some((m) => m.direction === "inbound")} onClick={suggest}><Sparkles aria-hidden /> Suggest a reply</Button>
              <span className="ml-auto text-xs text-muted-foreground">Sending from {conversation.accountName ?? "this account"}</span>
              <Button type="submit" disabled={!text.trim()} loading={actions.reply.isPending}>Send reply</Button>
            </div>
            <p className="text-xs text-muted-foreground">
              A suggested reply is written by {cost.data?.provider ?? "the template"} and {cost.data && cost.data.estimatedUsd > 0 ? `costs about $${cost.data.estimatedUsd}` : "costs nothing"}. It only fills this box: you decide whether to send it. Replies are checked against the sender&apos;s limits.
            </p>
          </>
        )}
      </form>
    </div>
  );
}
