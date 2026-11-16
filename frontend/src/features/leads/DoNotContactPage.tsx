import { useId, useState } from "react";
import { Download, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/utils/format";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { DNC_PAGE, dncService, useDnc, useDncActions, type DncKind, type DncResult } from "./dnc";

const KINDS: { id: DncKind; label: string; noun: string; hint: string; example: string }[] = [
  { id: "person", label: "People", noun: "profile", hint: "One LinkedIn profile link per line. Repeats are ignored.", example: "https://www.linkedin.com/in/someone" },
  { id: "company", label: "Companies", noun: "company", hint: "One company name or LinkedIn company page per line. Everyone Synex finds at that company is left out.", example: "Acme Inc" },
];

const summary = (r: DncResult, noun: string) => `${r.added} added, ${r.alreadyListed} already listed, ${r.invalid} skipped as not a valid ${noun}.`;

/** Nobody on this list is ever contacted: not imported, not started in a campaign, and any action still waiting is dropped. */
export function DoNotContactPage() {
  const id = useId();
  const [kind, setKind] = useState<DncKind>("person");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [removing, setRemoving] = useState<{ id: string; label: string } | null>(null);
  const query = useDnc(kind, search, offset);
  const actions = useDncActions();
  const meta = KINDS.find((k) => k.id === kind)!;
  const data = query.data;

  const exportCsv = async () => {
    try {
      const url = URL.createObjectURL(new Blob([await dncService.exportCsv(kind)], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `synex-do-not-contact-${kind === "person" ? "people" : "companies"}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(requestFailureMessage(error));
    }
  };
  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 2_000_000) return void toast.error("Choose a file smaller than 2 MB.");
    actions.importCsv.mutate({ kind, csv: await file.text() }, { onSuccess: (r) => toast.success(summary(r, meta.noun)), onError: (e) => toast.error(requestFailureMessage(e)) });
  };

  return (
    <div className="grid grid-cols-1 gap-4">
      <p className="text-sm text-muted-foreground">
        Everyone here is left out of imports, never starts a campaign, and any action already waiting for them is cancelled. Companies are matched by name, ignoring case and punctuation.
      </p>
      <div role="group" aria-label="List to show" className="flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <Button key={k.id} size="sm" variant={kind === k.id ? "default" : "outline"} aria-pressed={kind === k.id} onClick={() => { setKind(k.id); setOffset(0); setSearch(""); }}>{k.label}</Button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-0 flex-1 gap-1 sm:max-w-xs">
          <label htmlFor={`${id}-q`} className="text-sm font-medium">Search</label>
          <Input id={`${id}-q`} type="search" placeholder={kind === "person" ? "Name or profile link" : "Company"} value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} />
        </div>
        <Button size="sm" onClick={() => { setText(""); setAdding(true); }}>{kind === "person" ? "Add profiles" : "Add companies"}</Button>
        <Button size="sm" variant="outline" disabled={actions.importCsv.isPending} onClick={() => document.getElementById(`${id}-file`)?.click()}><Upload aria-hidden /> Import CSV</Button>
        <input id={`${id}-file`} type="file" accept=".csv,text/csv" className="sr-only" tabIndex={-1} aria-label={`Import a CSV with a ${kind === "person" ? "linkedin_url" : "company"} column`} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} />
        <Button size="sm" variant="outline" disabled={!data?.total} onClick={() => void exportCsv()}><Download aria-hidden /> Export</Button>
      </div>
      {query.isLoading && <Skeleton className="h-32 w-full" />}
      {query.isError && <p role="alert" className="text-sm text-danger">{requestFailureMessage(query.error)}</p>}
      {data && data.items.length === 0 && (
        <p className="rounded-lg border border-border p-4 text-sm text-muted-foreground">{search ? "No one matches that search." : `No ${meta.label.toLowerCase()} on the list yet.`}</p>
      )}
      {data && data.items.length > 0 && (
        <div tabIndex={0} role="region" aria-label={`${meta.label} not to contact (scrolls sideways)`} className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">{meta.label} on the do-not-contact list, {data.total} in total</caption>
            <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{kind === "person" ? "Profile" : "Company"}</th>
                <th scope="col" className="px-3 py-2 font-medium">Source</th>
                <th scope="col" className="px-3 py-2 font-medium">Added</th>
                <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => {
                const label = row.profileUrl ?? row.name;
                return (
                  <tr key={row.id} className="border-t border-border">
                    <th scope="row" className="px-3 py-2 text-left font-medium"><span className="break-all">{label}</span></th>
                    <td className="px-3 py-2 capitalize">{row.source}</td>
                    <td className="px-3 py-2">{formatDate(row.addedAt, "PP")}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="icon-sm" variant="ghost" aria-label={`Remove ${label}`} onClick={() => setRemoving({ id: row.id, label })}><Trash2 /></Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > DNC_PAGE && (
        <div className="flex items-center gap-3 text-sm">
          <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - DNC_PAGE))}>Previous</Button>
          <span>{offset + 1} to {Math.min(offset + DNC_PAGE, data.total)} of {data.total}</span>
          <Button size="sm" variant="outline" disabled={offset + DNC_PAGE >= data.total} onClick={() => setOffset(offset + DNC_PAGE)}>Next</Button>
        </div>
      )}

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{kind === "person" ? "Add profiles" : "Add companies"}</DialogTitle>
            <DialogDescription>{meta.hint}</DialogDescription>
          </DialogHeader>
          <label htmlFor={`${id}-text`} className="text-sm font-medium">{kind === "person" ? "Profile links" : "Companies"}</label>
          <Textarea id={`${id}-text`} rows={6} value={text} placeholder={meta.example} onChange={(e) => setText(e.target.value)} />
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setAdding(false)}>Cancel</Button>
            <Button disabled={!text.trim()} loading={actions.add.isPending}
              onClick={() => actions.add.mutate({ kind, text }, { onSuccess: (r) => { toast.success(summary(r, meta.noun)); setAdding(false); }, onError: (e) => toast.error(requestFailureMessage(e)) })}>
              Add to list
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Remove from the do-not-contact list?"
        description={removing ? `${removing.label} can be imported and contacted again after this.` : undefined}
        confirmLabel="Remove"
        destructive
        loading={actions.remove.isPending}
        onConfirm={() => removing && actions.remove.mutate(removing.id, { onSuccess: () => { toast.success("Removed."); setRemoving(null); }, onError: (e) => toast.error(requestFailureMessage(e)) })}
      />
    </div>
  );
}
