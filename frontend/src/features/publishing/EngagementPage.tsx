import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";
import { formatRelative } from "@/utils/format";

interface Item { id: string; account: string; postUrl: string; reaction: string | null; comment: string | null; status: string; detail: string | null; createdAt: string }
interface History { items: Item[]; reactions: string[]; maxComment: number }
interface Sender { id: string; name: string; status: string }

const LABEL: Record<string, string> = { like: "Like", celebrate: "Celebrate", support: "Support", love: "Love", insightful: "Insightful", funny: "Funny" };
const STATUS: Record<string, string> = { queued: "Waiting for the sender", done: "Done", failed: "Did not happen", cancelled: "Cancelled" };

/** React to a post or comment on it from one of your sender accounts, by hand. It runs within that sender's limits; the history says what happened. */
export function EngagementPage() {
  const qc = useQueryClient();
  const senders = useQuery({ queryKey: ["sender-accounts"], queryFn: () => api.get<Sender[]>("/linkedin-accounts"), retry: false });
  const history = useQuery({ queryKey: ["engagement"], queryFn: () => api.get<History>("/engagement"), retry: false, refetchInterval: (q) => (q.state.data?.items.some((i) => i.status === "queued") ? 5000 : false) });
  const [accountId, setAccountId] = useState("");
  const [postUrl, setPostUrl] = useState("");
  const [reaction, setReaction] = useState("");
  const [comment, setComment] = useState("");
  const max = history.data?.maxComment ?? 1250;
  const chosen = accountId || senders.data?.[0]?.id || "";
  const refresh = () => qc.invalidateQueries({ queryKey: ["engagement"] });
  const send = useMutation({
    mutationFn: () => api.post("/engagement", { accountId: chosen, postUrl: postUrl.trim(), reaction: reaction || null, comment: comment.trim() || null }),
    onSuccess: () => { toast.success("Queued. The sender does it within its limits."); setPostUrl(""); setComment(""); setReaction(""); void refresh(); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const cancel = useMutation({ mutationFn: (id: string) => api.delete(`/engagement/${id}`), onSuccess: () => { toast.success("Cancelled."); void refresh(); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const ready = !!chosen && !!postUrl.trim() && (!!reaction || !!comment.trim());

  return (
    <div className="grid gap-6">
      <section aria-labelledby="eng-h" className="grid max-w-2xl gap-3 rounded-lg border border-border bg-surface p-4">
        <h2 id="eng-h" className="text-base font-semibold">React or comment</h2>
        <p className="text-sm text-muted-foreground">Choose who reacts, paste the post&apos;s address, and choose a reaction, write a comment, or both. It counts toward that sender&apos;s limit for reactions and comments.</p>
        {senders.data?.length === 0 && <p role="note" className="text-sm">Connect a sender account first, under Sender accounts.</p>}
        <div className="grid gap-1 sm:max-w-xs">
          <label htmlFor="eng-account" className="text-sm font-medium">React as</label>
          <NativeSelect id="eng-account" value={chosen} onChange={(e) => setAccountId(e.target.value)} disabled={!senders.data?.length}>
            {(senders.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </NativeSelect>
        </div>
        <div className="grid gap-1">
          <label htmlFor="eng-url" className="text-sm font-medium">Post address</label>
          <Input id="eng-url" value={postUrl} placeholder="https://www.linkedin.com/feed/update/urn:li:activity:..." onChange={(e) => setPostUrl(e.target.value)} />
        </div>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium">Reaction</legend>
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-1 text-sm"><input type="radio" name="eng-reaction" checked={reaction === ""} onChange={() => setReaction("")} /> None</label>
            {(history.data?.reactions ?? Object.keys(LABEL)).map((r) => (
              <label key={r} className="flex items-center gap-1 text-sm"><input type="radio" name="eng-reaction" checked={reaction === r} onChange={() => setReaction(r)} /> {LABEL[r] ?? r}</label>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-1">
          <label htmlFor="eng-comment" className="text-sm font-medium">Comment (optional)</label>
          <Textarea id="eng-comment" rows={3} maxLength={max} value={comment} onChange={(e) => setComment(e.target.value)} />
          <span className="text-xs text-muted-foreground">{comment.length} of {max} characters. Your own words: Synex does not write or change them.</span>
        </div>
        <div><Button disabled={!ready} loading={send.isPending} onClick={() => send.mutate()}>Queue</Button></div>
      </section>

      <section aria-labelledby="eng-history" className="grid gap-2">
        <h2 id="eng-history" className="text-base font-semibold">History</h2>
        {history.isLoading && <Skeleton className="h-24 w-full" aria-label="Loading the history" />}
        {history.isError && <div role="alert" className="flex items-center gap-3 text-sm text-danger">The history could not be loaded. <Button size="sm" variant="outline" onClick={() => void history.refetch()}>Try again</Button></div>}
        {history.data?.items.length === 0 && <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Nothing yet. Reactions and comments you queue appear here.</p>}
        {!!history.data?.items.length && (
          <ul aria-label="Reactions and comments" className="grid gap-2">
            {history.data.items.map((i) => (
              <li key={i.id} className="grid gap-1 rounded-lg border border-border p-3 text-sm">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{i.account}</span>
                  {i.reaction && <span>{LABEL[i.reaction] ?? i.reaction}</span>}
                  <span className={i.status === "failed" ? "text-danger" : "text-muted-foreground"}>{STATUS[i.status] ?? i.status}{i.detail ? `: ${i.detail}` : ""}</span>
                  <time className="text-xs text-muted-foreground" dateTime={i.createdAt}>{formatRelative(i.createdAt)}</time>
                  {i.status === "queued" && <Button size="sm" variant="ghost" className="text-danger" onClick={() => cancel.mutate(i.id)}>Cancel</Button>}
                </span>
                <span className="break-all text-xs text-muted-foreground">{i.postUrl}</span>
                {i.comment && <span className="whitespace-pre-wrap">{i.comment}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
