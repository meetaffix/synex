import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api, ApiError } from "@/services/client";
import { Thread, type Feedback } from "./ReviewPanel";

interface Page { reviewer: string; post: { title: string; body: string; status: string; version: number; scheduledAt: string | null }; thread: Feedback[]; expiresAt: string }

/** The reviewer's page, opened from a private link. No account and no app shell: just the post and a way to answer. */
export function ReviewPage() {
  const { token = "" } = useParams();
  const qc = useQueryClient();
  const page = useQuery({ queryKey: ["review", token], queryFn: () => api.get<Page>(`/review/${encodeURIComponent(token)}`), retry: false });
  const [text, setText] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (decision: Feedback["decision"]) => api.post(`/review/${encodeURIComponent(token)}/feedback`, { decision, body: text.trim() }),
    onSuccess: (_r, decision) => { setText(""); setSent(decision === "approve" ? "Thank you. Your approval was sent." : decision === "changes" ? "Thank you. Your request for changes was sent." : "Thank you. Your comment was sent."); void qc.invalidateQueries({ queryKey: ["review", token] }); },
  });
  return (
    <main id="main-content" className="mx-auto grid w-full max-w-2xl gap-6 px-4 py-10">
      {page.isLoading && <Skeleton className="h-64 w-full" aria-label="Loading the post" />}
      {page.isError && (
        <div role="alert" className="grid gap-2 rounded-lg border border-border p-6">
          <h1 className="text-xl font-semibold">This review link does not work</h1>
          <p className="text-sm text-muted-foreground">{page.error instanceof ApiError && page.error.status === 404 ? page.error.message : requestFailureMessage(page.error)}</p>
        </div>
      )}
      {page.data && (
        <>
          <header className="grid gap-1">
            <p className="text-sm text-muted-foreground">Hello {page.data.reviewer}, you were asked to review this LinkedIn post.</p>
            <h1 className="text-2xl font-semibold">{page.data.post.title || "Untitled post"}</h1>
          </header>
          <article aria-label="Post" className="whitespace-pre-wrap rounded-lg border border-border bg-surface p-4 text-sm">{page.data.post.body || "This post has no text yet."}</article>
          <section aria-labelledby="answer-h" className="grid gap-2">
            <h2 id="answer-h" className="text-base font-semibold">Your answer</h2>
            <label htmlFor="review-text" className="text-sm font-medium">Comment</label>
            <Textarea id="review-text" rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="What works, and what should change?" />
            <div className="flex flex-wrap gap-2">
              <Button loading={send.isPending && send.variables === "approve"} onClick={() => send.mutate("approve")}>Approve</Button>
              <Button variant="outline" disabled={!text.trim()} loading={send.isPending && send.variables === "changes"} onClick={() => send.mutate("changes")}>Request changes</Button>
              <Button variant="ghost" disabled={!text.trim()} loading={send.isPending && send.variables === "comment"} onClick={() => send.mutate("comment")}>Send comment</Button>
            </div>
            {sent && <p role="status" className="text-sm text-success">{sent}</p>}
            {send.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(send.error)}</p>}
          </section>
          <section aria-labelledby="thread-h" className="grid gap-2">
            <h2 id="thread-h" className="text-base font-semibold">Feedback so far</h2>
            <Thread items={page.data.thread} />
          </section>
        </>
      )}
    </main>
  );
}
