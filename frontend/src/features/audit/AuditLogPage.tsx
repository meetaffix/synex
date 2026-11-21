import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api, ApiError } from "@/services/client";
import { formatRelative } from "@/utils/format";

interface Item { id: string; at: string; source: "linkedin" | "assistant" | "settings"; who: string; action: string; status: string; detail: string }
interface Page { items: Item[]; total: number; limit: number; offset: number; canDelete: boolean }

const PAGE = 25;
const SOURCES = [["all", "Everything"], ["sends", "Messages and invitations"], ["linkedin", "All LinkedIn actions"], ["assistant", "Assistant changes"], ["settings", "Settings"]] as const;
const SOURCE_LABEL: Record<string, string> = { linkedin: "LinkedIn", assistant: "Assistant", settings: "Settings" };
const failure = (e: unknown) => (e instanceof ApiError && e.message ? e.message : requestFailureMessage(e));

const csvCell = (v: string) => `"${v.replaceAll('"', '""')}"`;

/** Everything done in this workspace, newest first: actions on LinkedIn, what the assistant changed, and settings changes. An admin can delete it all. */
export function AuditLogPage() {
  const qc = useQueryClient();
  const [source, setSource] = useState<string>("sends"); // what reached people first; the reads of the inbox are one filter away
  const [offset, setOffset] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const [word, setWord] = useState("");
  const log = useQuery({ queryKey: ["audit", source, offset], queryFn: () => api.get<Page>(`/audit?limit=${PAGE}&offset=${offset}&source=${source}`), retry: false });
  const clear = useMutation({
    mutationFn: () => api.delete<{ removed: number }>("/audit", { confirm: word }),
    onSuccess: async (out) => { await qc.invalidateQueries({ queryKey: ["audit"] }); setOffset(0); setDeleting(false); setWord(""); toast.success(`Audit log deleted: ${out.removed} entries removed.`); },
    onError: (e) => toast.error(failure(e)),
  });
  const exportCsv = async () => {
    try {
      const all = await api.get<Page>(`/audit?limit=200&offset=0&source=${source}`);
      const rows = [["When", "Source", "Who", "Action", "Result", "Details"], ...all.items.map((i) => [i.at, SOURCE_LABEL[i.source], i.who, i.action, i.status, i.detail])];
      const blob = new Blob([rows.map((r) => r.map(csvCell).join(",")).join("\n")], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "synex-audit-log.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { toast.error(failure(e)); }
  };
  const data = log.data;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeader title="Audit log" description="Everything done on LinkedIn and every change made here."
        actions={
          <>
            <Button variant="outline" onClick={() => void exportCsv()} disabled={!data || data.total === 0}><Download aria-hidden /> Export CSV</Button>
            {data?.canDelete && <Button variant="outline" className="text-danger" onClick={() => setDeleting(true)}><Trash2 aria-hidden /> Delete audit log</Button>}
          </>
        } />
      <div className="grid max-w-xs gap-1">
        <Label htmlFor="audit-source">Show</Label>
        <NativeSelect id="audit-source" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
          {SOURCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </NativeSelect>
      </div>
      {log.isLoading && <Skeleton className="h-40 w-full" aria-label="Loading the audit log" />}
      {log.isError && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">The audit log could not be loaded. <Button size="sm" variant="outline" onClick={() => void log.refetch()}>Try again</Button></div>}
      {data && data.items.length === 0 && <p role="status" className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Nothing here yet. Actions and changes appear as they happen.</p>}
      {data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Audit log (scrolls sideways)">
            <table className="w-full min-w-[44rem] text-sm">
              <caption className="sr-only">Audit log entries, newest first</caption>
              <thead><tr className="text-left text-muted-foreground">{["When", "Source", "Who", "Action", "Result", "Details"].map((h) => <th key={h} scope="col" className="py-2 pr-3 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id} className="border-t border-border align-top">
                    <td className="py-2 pr-3"><time dateTime={i.at} title={i.at}>{formatRelative(i.at)}</time></td>
                    <td className="py-2 pr-3">{SOURCE_LABEL[i.source]}</td>
                    <td className="py-2 pr-3">{i.who}</td>
                    <th scope="row" className="py-2 pr-3 text-left font-normal">{i.action.replaceAll("_", " ")}</th>
                    <td className={["ok", "applied", "proposed"].includes(i.status) ? "py-2 pr-3" : "py-2 pr-3 text-danger"}>{i.status.replaceAll("_", " ")}</td>
                    <td className="py-2 text-muted-foreground">{i.detail || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span role="status">{offset + 1} to {Math.min(offset + PAGE, data.total)} of {data.total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</Button>
              <Button size="sm" variant="outline" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Older</Button>
            </div>
          </div>
        </>
      )}
      <Dialog open={deleting} onOpenChange={(open) => { setDeleting(open); if (!open) setWord(""); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete the whole audit log?</DialogTitle>
            <DialogDescription>Every entry is removed and cannot be brought back. One line stays, saying who cleared it and how many entries were removed. Campaigns, leads and limits are not touched.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1">
            <Label htmlFor="audit-confirm">Type DELETE to confirm</Label>
            <Input id="audit-confirm" autoComplete="off" value={word} onChange={(e) => setWord(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(false)}>Keep it</Button>
            <Button variant="destructive" disabled={word !== "DELETE"} loading={clear.isPending} onClick={() => clear.mutate()}>Delete audit log</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
