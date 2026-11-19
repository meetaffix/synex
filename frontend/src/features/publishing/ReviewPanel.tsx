import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";
import { formatRelative } from "@/utils/format";

export interface Feedback { id: string; author: string; decision: "comment" | "approve" | "changes"; body: string; postVersion: number | null; createdAt: string; fromReviewer: boolean }
interface ReviewLink { id: string; reviewer: string; state: "active" | "revoked" | "expired"; expiresAt: string; lastSeenAt: string | null }
interface Reviews { links: ReviewLink[]; thread: Feedback[]; approvedBy: string[] }

export const DECISION_LABEL: Record<Feedback["decision"], string> = { comment: "Comment", approve: "Approved", changes: "Asked for changes" };

/** The feedback thread, shared by the owner's panel and the reviewer's page. */
export function Thread({ items }: { items: Feedback[] }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No feedback yet.</p>;
  return (
    <ol aria-label="Feedback" className="grid gap-2">
      {items.map((f) => (
        <li key={f.id} className="grid gap-0.5 rounded-md bg-surface-muted p-2 text-sm">
          <span className="flex flex-wrap items-center gap-2"><span className="font-medium">{f.author}</span>
            {f.decision !== "comment" && <span className={f.decision === "approve" ? "text-success" : "text-warning"}>{DECISION_LABEL[f.decision]}</span>}
            <time className="text-xs text-muted-foreground" dateTime={f.createdAt}>{formatRelative(f.createdAt)}</time></span>
          {f.body && <span className="whitespace-pre-wrap">{f.body}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Invite reviewers to a post with a private link, see what they said, and reply. Approval is recorded; you still publish. */
export function ReviewPanel({ postId }: { postId: string }) {
  const qc = useQueryClient();
  const key = ["publishing", "reviews", postId];
  const reviews = useQuery({ queryKey: key, queryFn: () => api.get<Reviews>(`/publishing/posts/${postId}/reviews`), retry: false });
  const [name, setName] = useState("");
  const [reply, setReply] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const invite = useMutation({
    mutationFn: () => api.post<{ path: string }>(`/publishing/posts/${postId}/reviewers`, { reviewer: name.trim() }),
    onSuccess: (r) => { setFresh(`${window.location.origin}${r.path}`); setName(""); void refresh(); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.delete(`/publishing/posts/${postId}/reviewers/${id}`), onSuccess: () => { toast.success("Link revoked."); void refresh(); } });
  const send = useMutation({ mutationFn: () => api.post(`/publishing/posts/${postId}/feedback`, { body: reply.trim() }), onSuccess: () => { setReply(""); void refresh(); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const data = reviews.data;
  return (
    <section aria-labelledby={`rev-${postId}`} className="grid gap-3 rounded-lg border border-border bg-surface p-4">
      <h2 id={`rev-${postId}`} className="text-base font-semibold">Reviewers</h2>
      <p className="text-sm text-muted-foreground">Send someone a private link to read this post and comment, approve or ask for changes. They need no account. An approval is recorded; you still publish.</p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1"><label htmlFor={`rev-name-${postId}`} className="text-sm font-medium">Reviewer name</label>
          <Input id={`rev-name-${postId}`} maxLength={80} value={name} placeholder="For example, Priya" onChange={(e) => setName(e.target.value)} /></div>
        <Button size="sm" disabled={!name.trim()} loading={invite.isPending} onClick={() => invite.mutate()}>Create review link</Button>
      </div>
      {fresh && <p role="status" className="rounded-md bg-primary-soft p-2 text-sm text-primary-soft-foreground">Copy this link now. It is shown only once and works for 14 days: <code className="break-all">{fresh}</code></p>}
      {reviews.isError && <p role="alert" className="text-sm text-danger">Reviews could not be loaded.</p>}
      {data && (
        <>
          {data.approvedBy.length > 0 && <p className="text-sm text-success">Approved as it is now by {data.approvedBy.join(", ")}.</p>}
          {data.links.length > 0 && (
            <ul aria-label="Review links" className="grid gap-1 text-sm">
              {data.links.map((l) => (
                <li key={l.id} className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{l.reviewer}</span>
                  <span className="text-muted-foreground">{l.state === "active" ? (l.lastSeenAt ? `opened ${formatRelative(l.lastSeenAt)}` : "not opened yet") : l.state}</span>
                  {l.state === "active" && <Button size="sm" variant="ghost" className="text-danger" onClick={() => revoke.mutate(l.id)}>Revoke</Button>}
                </li>
              ))}
            </ul>
          )}
          <Thread items={data.thread} />
          <div className="grid gap-1">
            <label htmlFor={`rev-reply-${postId}`} className="text-sm font-medium">Reply</label>
            <Textarea id={`rev-reply-${postId}`} rows={2} maxLength={2000} value={reply} onChange={(e) => setReply(e.target.value)} />
            <div><Button size="sm" variant="outline" disabled={!reply.trim()} loading={send.isPending} onClick={() => send.mutate()}>Send reply</Button></div>
          </div>
        </>
      )}
    </section>
  );
}
