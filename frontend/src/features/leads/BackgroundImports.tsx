import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api } from "@/services/client";

interface Collection {
  id: string; source: string; label: string; status: string; listName: string; limit: number;
  fetched: number; created: number; detail: string | null; listId?: string | null; estimate?: { people: number };
}

const ACTIVE = ["previewing", "queued", "running"];
/** Each finished import is announced once, whether the dialog or this card notices first. */
const announced = new Set<string>();
export function announceFinished(c: { id: string; status: string; created: number; listName: string; detail?: string | null }) {
  if (announced.has(c.id)) return;
  announced.add(c.id);
  if (c.status === "completed") toast.success(`${c.created} leads added to ${c.listName}.`);
  else if (c.status === "failed") toast.error(c.detail ?? "The import stopped early. What was found is kept.");
}
const list = (data: unknown): Collection[] => (Array.isArray(data) ? (data as Collection[]) : []);

/** Imports that read LinkedIn take minutes. They run in the background: this card follows them on every page, with the live count, and says when they finish. */
export function BackgroundImports() {
  const client = useQueryClient();
  const known = useRef<Map<string, string>>(new Map());
  const { data } = useQuery({
    queryKey: ["lead-collections", "recent"],
    queryFn: () => api.get<Collection[]>("/lead-collections"),
    retry: false,
    refetchInterval: (query) => (list(query.state.data).some((c) => ACTIVE.includes(c.status)) ? 3000 : 20000),
  });
  const active = list(data).filter((c) => ACTIVE.includes(c.status));

  // Say so when one that was running ends, and refresh the lists it filled.
  useEffect(() => {
    for (const c of list(data)) {
      const before = known.current.get(c.id);
      known.current.set(c.id, c.status);
      if (!before || !ACTIVE.includes(before) || ACTIVE.includes(c.status)) continue;
      announceFinished(c);
      if (c.status === "completed") { void client.invalidateQueries({ queryKey: ["leads"] }); void client.invalidateQueries({ queryKey: ["lead-lists"] }); }
    }
  }, [data, client]);

  if (active.length === 0) return null;
  const stop = async (id: string) => { await api.post(`/lead-collections/${id}/stop`, {}); void client.invalidateQueries({ queryKey: ["lead-collections"] }); };
  return (
    <aside aria-label="Imports in progress" className="fixed bottom-4 right-4 z-40 grid w-[min(22rem,calc(100vw-2rem))] gap-3">
      {active.map((c) => {
        const total = c.estimate?.people && c.estimate.people > c.fetched && c.source !== "connections" ? c.estimate.people : null;
        const percent = total ? Math.min(100, Math.round((c.fetched / total) * 100)) : null;
        return (
          <div key={c.id} role="status" className="grid gap-2 rounded-lg border border-border bg-surface p-4 shadow-float">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-semibold"><Loader2 className="size-4 shrink-0 animate-spin text-primary-ink" aria-hidden />{c.source === "connections" ? "Importing your connections" : `Importing from ${c.label}`}</p>
                <p className="truncate text-xs text-muted-foreground">Into “{c.listName}”. You can keep working.</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => void stop(c.id)}>Stop</Button>
            </div>
            <p className="text-2xl font-semibold tabular-nums">{c.fetched.toLocaleString()} <span className="text-sm font-normal text-muted-foreground">{c.status === "queued" ? "waiting to start" : c.status === "previewing" ? "reading the first results" : total ? `of about ${total.toLocaleString()} found` : "found so far"}</span></p>
            {percent !== null ? <Progress value={percent} aria-label={`${percent}% of the import found`} /> : <div className="h-2 overflow-hidden rounded-full bg-surface-muted" aria-hidden><div className="h-full w-1/3 animate-[shimmer_1.4s_infinite] rounded-full bg-primary" /></div>}
            {c.detail && <p className="text-xs text-muted-foreground">{c.detail}</p>}
          </div>
        );
      })}
    </aside>
  );
}
