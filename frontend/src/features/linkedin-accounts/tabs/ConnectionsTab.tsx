import { useId, useState } from "react";
import { Download, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/utils/format";
import { requestFailureMessage } from "../copy";
import { PAGE_SIZE, connectionsService, useConnectionActions, useConnections, type ConnectionKind } from "../connections";

const KINDS: { id: ConnectionKind; label: string }[] = [
  { id: "connection", label: "Connections" },
  { id: "invitation", label: "Received invitations" },
];

/** The people connected to this account, and the invitations waiting for it, as Synex has read them. */
export function ConnectionsTab({ accountId, disabled }: { accountId: string; disabled: boolean }) {
  const id = useId();
  const [kind, setKind] = useState<ConnectionKind>("connection");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useConnections(accountId, kind, search, offset);
  const actions = useConnectionActions(accountId);
  const data = query.data;
  const busy = data?.sync.status === "queued" || data?.sync.status === "running";
  const heading = KINDS.find((item) => item.id === kind)!.label;
  const label = heading.toLowerCase();

  const reload = () =>
    actions.reload.mutate(kind, {
      onSuccess: () => toast.success(`Reading ${label} has been queued.`),
      onError: (error) => toast.error(requestFailureMessage(error)),
    });
  const exportCsv = async () => {
    try {
      const blob = new Blob([await connectionsService.exportCsv(accountId, kind)], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `synex-${kind === "connection" ? "connections" : "invitations"}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(requestFailureMessage(error));
    }
  };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 2_000_000) return void toast.error("Choose a file smaller than 2 MB.");
    actions.importCsv.mutate(await file.text(), {
      onSuccess: (r) => toast.success(`${r.added} added, ${r.alreadyStored} already stored, ${r.duplicatesInFile} repeated in the file, ${r.invalid} skipped as not a LinkedIn profile link.`),
      onError: (error) => toast.error(requestFailureMessage(error)),
    });
  };

  const statusText = busy
    ? "Synex is reading this list now."
    : data?.sync.status === "failed"
      ? `The last read did not finish. ${data.sync.detail ?? ""}`
      : data?.sync.lastSyncedAt
        ? `Last read ${formatRelative(data.sync.lastSyncedAt)}, ${data.sync.lastAdded ?? 0} people.`
        : "Not read yet.";

  return (
    <div className="grid grid-cols-1 gap-4">
      <div role="group" aria-label="List to show" className="flex flex-wrap gap-2">
        {KINDS.map((item) => (
          <Button key={item.id} size="sm" variant={kind === item.id ? "default" : "outline"} aria-pressed={kind === item.id} onClick={() => { setKind(item.id); setOffset(0); }}>
            {item.label}
          </Button>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">{data?.note ?? "Synex reads your connections a little at a time, so a long list takes a while to fill."}</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-0 flex-1 gap-1 sm:max-w-xs">
          <label htmlFor={`${id}-q`} className="text-sm font-medium">Search</label>
          <Input id={`${id}-q`} type="search" placeholder="Name, headline or place" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} />
        </div>
        <Button size="sm" variant="secondary" loading={actions.reload.isPending} disabled={disabled || busy} onClick={reload}>
          <RefreshCw aria-hidden /> {busy ? "Reading" : `Reload ${label}`}
        </Button>
        <Button size="sm" variant="outline" disabled={!data?.total} onClick={() => void exportCsv()}><Download aria-hidden /> Export CSV</Button>
        <Button size="sm" variant="outline" disabled={actions.importCsv.isPending} onClick={() => document.getElementById(`${id}-file`)?.click()}>
          <Upload aria-hidden /> Upload CSV
        </Button>
        <input id={`${id}-file`} type="file" accept=".csv,text/csv" className="sr-only" tabIndex={-1} aria-label="Upload a CSV with a linkedin_url column" onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }} />
      </div>
      <p role="status" className="text-sm text-muted-foreground">{statusText}</p>
      {query.isLoading && <Skeleton className="h-40 w-full" />}
      {query.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(query.error)}</p>}
      {data && data.items.length === 0 && (
        <p className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
          {search ? "No one matches that search." : "Nothing stored yet. Reload to have Synex read this list, or upload a CSV with a linkedin_url column."}
        </p>
      )}
      {data && data.items.length > 0 && (
        <div tabIndex={0} role="region" aria-label={`${heading} (scrolls sideways)`} className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">{heading}, {data.total} stored</caption>
            <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Name</th>
                <th scope="col" className="px-3 py-2 font-medium">Headline</th>
                <th scope="col" className="px-3 py-2 font-medium">Location</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.id} className="border-t border-border">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <a className="underline-offset-2 hover:underline" href={row.profileUrl} target="_blank" rel="noreferrer noopener">{row.name}</a>
                  </th>
                  <td className="px-3 py-2">{row.headline}</td>
                  <td className="px-3 py-2">{row.location}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center gap-3 text-sm">
          <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
          <span>{offset + 1} to {Math.min(offset + PAGE_SIZE, data.total)} of {data.total}</span>
          <Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
        </div>
      )}
    </div>
  );
}
