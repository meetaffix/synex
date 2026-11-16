import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";

interface Status { reachable: boolean; model: string; installed: boolean }
interface Proposal { id: string; summary: string; changes: string[]; status: string }
interface Turn { role: "user" | "assistant"; content: string }

/** The free option: a model on this computer or network answers typed requests with the same tools and confirmation cards. No paid service. */
export function LocalAssistantCard() {
  const status = useQuery({ queryKey: ["assistant", "local-status"], queryFn: () => api.get<Status>("/assistant/local/status"), retry: false });
  const [text, setText] = useState("");
  const [history, setHistory] = useState<Turn[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const chat = useMutation({
    mutationFn: (message: string) => api.post<{ reply: string; cards: { type: string; proposal?: Proposal }[] }>("/assistant/local/chat", { text: message, history }),
    onSuccess: (r, message) => {
      setHistory((h) => [...h, { role: "user", content: message }, { role: "assistant", content: r.reply }]);
      setProposals((p) => [...p, ...r.cards.filter((c) => c.type === "proposal" && c.proposal).map((c) => c.proposal!)]);
      setText("");
    },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const decide = useMutation({
    mutationFn: (v: { id: string; action: "confirm" | "cancel" }) => api.post(`/assistant/proposals/${v.id}/${v.action}`),
    onSuccess: (_r, v) => { setProposals((p) => p.filter((x) => x.id !== v.id)); toast.success(v.action === "confirm" ? "Done." : "Cancelled. Nothing changed."); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const ready = status.data?.reachable && status.data.installed;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Free local model</CardTitle>
        <CardDescription>
          Type to the assistant using a model running on your own computer (Ollama). It uses the same tools, permissions and confirmation cards as the voice assistant, costs nothing, and sends nothing outside your network.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <p role="status" className="text-sm">
          {status.isLoading ? "Checking the local model." : ready ? `Ready: ${status.data?.model} is running.` : status.data?.reachable ? `Ollama is running but the model ${status.data.model} is not installed. Run: ollama pull ${status.data.model}` : "Ollama is not running. Install it from ollama.com, start it, then set OLLAMA_URL and OLLAMA_MODEL if you changed them."}
        </p>
        <ul aria-label="Conversation" className="grid gap-2 text-sm">
          {history.map((t, i) => <li key={i} className={t.role === "user" ? "font-medium" : "rounded-md bg-surface-muted p-2"}>{t.role === "user" ? `You: ${t.content}` : t.content}</li>)}
        </ul>
        {proposals.map((p) => (
          <div key={p.id} role="group" aria-label="Confirmation needed" className="grid gap-2 rounded-lg border border-border p-3 text-sm">
            <p className="font-medium">{p.summary}</p>
            <ul className="list-disc pl-5">{p.changes.map((c) => <li key={c}>{c}</li>)}</ul>
            <div className="flex gap-2">
              <Button size="sm" loading={decide.isPending} onClick={() => decide.mutate({ id: p.id, action: "confirm" })}>Confirm</Button>
              <Button size="sm" variant="outline" onClick={() => decide.mutate({ id: p.id, action: "cancel" })}>Cancel</Button>
            </div>
          </div>
        ))}
        <div className="grid gap-2">
          <label htmlFor="local-ask" className="text-sm font-medium">Ask the local assistant</label>
          <Textarea id="local-ask" rows={2} maxLength={2000} value={text} disabled={!ready} onChange={(e) => setText(e.target.value)} placeholder="For example: which conversations need a reply?" />
          <div><Button disabled={!ready || !text.trim()} loading={chat.isPending} onClick={() => chat.mutate(text.trim())}>Send</Button></div>
        </div>
      </CardContent>
    </Card>
  );
}
