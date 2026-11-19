import { useState } from "react";
import { Gift } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/services/client";

interface News { items: { id: string; date: string; title: string; body: string }[]; latestId: string; unread: boolean }

/** A short list of what changed, opened from the top bar. A dot shows until it has been opened since the newest entry. */
export function WhatsNew() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const news = useQuery({ queryKey: ["whats-new"], queryFn: () => api.get<News>("/integrations/whats-new"), staleTime: 60_000, retry: false });
  const seen = useMutation({ mutationFn: () => api.post("/integrations/whats-new/seen"), onSuccess: () => qc.invalidateQueries({ queryKey: ["whats-new"] }) });
  if (!news.data) return null; // no list, no button: nothing here is a placeholder
  const unread = news.data.unread;
  return (
    <>
      <Button variant="ghost" size="icon" className="relative" aria-label={unread ? "What's new, unread" : "What's new"} onClick={() => { setOpen(true); if (unread) seen.mutate(); }}>
        <Gift aria-hidden />
        {unread && <span aria-hidden className="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary" />}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle>What&apos;s new</DialogTitle>
            <DialogDescription>The latest changes, newest first.</DialogDescription>
          </DialogHeader>
          <ol aria-label="Changes" className="grid gap-4">
            {news.data.items.map((item) => (
              <li key={item.id} className="grid gap-1">
                <h3 className="text-sm font-semibold">{item.title}</h3>
                <p className="text-xs text-muted-foreground"><time dateTime={item.date}>{item.date}</time></p>
                <p className="text-sm">{item.body}</p>
              </li>
            ))}
          </ol>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
