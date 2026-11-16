import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { api } from "@/services/client";
import { leadListsService } from "@/services/resources";

interface Source {
  id: string;
  label: string;
  readsLinkedin: boolean;
  available: boolean;
  note: string | null;
  maxLeads: number | null;
  produces?: string;
}
interface Person {
  name: string;
  headline: string | null;
  company: string | null;
  location: string | null;
  degree: number | null;
  profileUrl: string;
}
interface Collection {
  id: string;
  status: string;
  listName: string;
  limit: number;
  fetched: number;
  created: number;
  skipped: Record<string, number>;
  detail: string | null;
  estimate: { people: number; pages: number; minutes: number; reads_linkedin: boolean };
  preview: { people: Person[]; total: number; degrees: Record<string, number> } | null;
  needsMapping?: { headers: string[]; suggested: Record<string, string>; rows: number };
}

const HINTS: Record<string, string> = {
  post: "Paste one or more LinkedIn post links, one per line.",
  search: "Paste a LinkedIn people-search results address.",
  connections: "Reads your own 1st-degree connections. Filters are optional.",
  urls: "Paste LinkedIn profile links, one per line or separated by commas.",
  csv: "Upload a CSV, paste its text, or paste a Google Sheets link (shared so anyone with the link can view).",
  lists: "Pick one or more of your existing lists.",
  inbox: "People you already have conversations with.",
  event: "Paste a LinkedIn event address. The sender account you choose must be marked as attending the event, or LinkedIn shows no attendee list.",
  own_posts: "Reads the people who reacted to or commented on your sender account's five most recent posts. Nothing to paste.",
  sales_navigator: "Paste a Sales Navigator people search or lead list address. Needs a Sales Navigator subscription on the sender account.",
  recruiter: "Paste a LinkedIn Recruiter search address. Needs a Recruiter licence on the sender account.",
  companies: "Paste a LinkedIn company search results address. This makes a list of companies, not people; no one is messaged.",
  sales_nav_accounts: "Paste a Sales Navigator account search address. This makes a list of companies, not people; no one is messaged.",
};
const URL_SOURCES = ["search", "event", "sales_navigator", "recruiter", "companies", "sales_nav_accounts"];
const PLACEHOLDER: Record<string, string> = {
  post: "https://www.linkedin.com/feed/update/urn:li:activity:…",
  search: "https://www.linkedin.com/search/results/people/?keywords=…",
  event: "https://www.linkedin.com/events/…",
  sales_navigator: "https://www.linkedin.com/sales/search/people?…",
  recruiter: "https://www.linkedin.com/talent/search?…",
  companies: "https://www.linkedin.com/search/results/companies/?keywords=…",
  sales_nav_accounts: "https://www.linkedin.com/sales/search/company?…",
  csv: "Paste CSV text or a Google Sheets link",
  urls: "https://www.linkedin.com/in/…",
};
const SKIP_LABELS: Record<string, string> = {
  degree_filter: "outside the chosen connection degrees",
  already_contacted: "already contacted",
  already_connected: "already connected",
  already_in_campaign: "already in a campaign",
};
const MAPPING_FIELDS: [string, string][] = [
  ["linkedin_url", "LinkedIn profile URL (required)"],
  ["name", "Full name"],
  ["first_name", "First name"],
  ["last_name", "Last name"],
  ["headline", "Headline or title"],
  ["company", "Company"],
  ["location", "Location"],
  ["email", "Email"],
];
const stamp = () => new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
const failure = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong. Try again.");

export function AddLeadsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient();
  const sources = useQuery({ queryKey: ["lead-sources"], queryFn: () => api.get<Source[]>("/lead-collections/sources"), enabled: open });
  const accounts = useSenderAccounts();
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list, enabled: open });
  const [source, setSource] = useState<Source | null>(null);
  const [text, setText] = useState("");
  const [reactions, setReactions] = useState<string[]>([]);
  const [comments, setComments] = useState(false);
  const [filters, setFilters] = useState({ title: "", company: "", location: "" });
  const [listIds, setListIds] = useState<string[]>([]);
  const [accountId, setAccountId] = useState("");
  const [listName, setListName] = useState("");
  const [limit, setLimit] = useState(50);
  const [skip, setSkip] = useState({ skip_in_campaign: false, skip_contacted: false, skip_connected: false });
  const [degrees, setDegrees] = useState<number[]>([1, 2, 3]);
  const [mapping, setMapping] = useState<Record<string, string> | null>(null);
  const [collection, setCollection] = useState<Collection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const poll = useRef<number | undefined>(undefined);

  const connected = (accounts.data ?? []).filter((a) => a.status === "connected");
  const estimate = useQuery({
    queryKey: ["lead-estimate", source?.id, limit, accountId],
    queryFn: () => api.get<{ people: number; pages: number; minutes: number; reads_linkedin: boolean; maxPagesPerRun: number; pagesLeftToday: number | null }>(`/lead-collections/estimate?source=${source?.id}&limit=${limit}${accountId ? `&accountId=${accountId}` : ""}`),
    enabled: open && !!source?.readsLinkedin,
  });
  const companies = source?.produces === "companies";
  useEffect(() => {
    if (!accountId && connected.length) setAccountId(connected[0].id);
  }, [connected, accountId]);
  useEffect(() => {
    if (source) {
      setListName(`${source.label} ${stamp()}`);
      setLimit(Math.min(50, source.maxLeads ?? 50));
    }
  }, [source]);
  useEffect(() => () => window.clearInterval(poll.current), []);

  const reset = () => {
    window.clearInterval(poll.current);
    setSource(null);
    setCollection(null);
    setMapping(null);
    setError(undefined);
    setText("");
  };
  const close = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const params = useMemo(() => {
    switch (source?.id) {
      case "post":
        return { urls: text.split(/\s+/).filter(Boolean), reactions, comments };
      case "own_posts":
        return {};
      case "connections":
        return { filters };
      case "csv":
        return /^https?:\/\//.test(text.trim()) ? { sheetUrl: text.trim(), mapping } : { text, mapping };
      case "lists":
        return { listIds };
      case "inbox":
        return {};
      default:
        return source && URL_SOURCES.includes(source.id) ? { url: text.trim() } : { text };
    }
  }, [source, text, reactions, comments, filters, listIds, mapping]);

  const watch = (id: string) => {
    window.clearInterval(poll.current);
    poll.current = window.setInterval(async () => {
      try {
        const next = await api.get<Collection>(`/lead-collections/${id}`);
        setCollection(next);
        if (["preview_ready", "completed", "failed", "stopped"].includes(next.status)) {
          window.clearInterval(poll.current);
          if (next.status === "completed") void client.invalidateQueries();
        }
      } catch {
        window.clearInterval(poll.current);
      }
    }, 3000);
  };

  const preview = async () => {
    if (!source) return;
    setBusy(true);
    setError(undefined);
    try {
      let made = await api.post<Collection>("/lead-collections", {
        source: source.id,
        accountId: source.readsLinkedin ? accountId : undefined,
        listName,
        limit,
        params,
        options: { ...skip, degrees },
      });
      if (made.needsMapping) {
        setMapping(made.needsMapping.suggested);
        setCollection(made);
        return;
      }
      if (source.readsLinkedin) {
        made = await api.post<Collection>(`/lead-collections/${made.id}/preview`, {});
        watch(made.id);
      }
      setCollection(made);
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!collection) return;
    setBusy(true);
    setError(undefined);
    try {
      const done = await api.post<Collection>(`/lead-collections/${collection.id}/run`, { listName, limit, options: { ...skip, degrees } });
      setCollection(done);
      if (done.status !== "completed") watch(done.id);
      else {
        await client.invalidateQueries();
        toast.success(`${done.created} leads added to ${done.listName}.`);
      }
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    if (collection) setCollection(await api.post<Collection>(`/lead-collections/${collection.id}/stop`, {}));
  };

  const working = collection && ["previewing", "queued", "running"].includes(collection.status);
  const people = collection?.preview?.people ?? [];
  const deg = collection?.preview?.degrees;
  const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogTitle>How would you like to add leads?</DialogTitle>
        <DialogDescription>Pick a source. You will see an estimate and a preview before anything is added.</DialogDescription>

        {!source && (
          <div className="grid gap-2 sm:grid-cols-2" role="list" aria-label="Lead sources">
            {sources.isLoading && <p className="text-sm text-muted-foreground">Loading sources…</p>}
            {(sources.data ?? []).map((s) => (
              <button
                key={s.id}
                role="listitem"
                type="button"
                disabled={!s.available}
                onClick={() => setSource(s)}
                className="rounded-md border border-border bg-surface p-3 text-left text-sm transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="block font-medium">{s.label}</span>
                <span className="block text-xs text-muted-foreground">{s.available ? (s.readsLinkedin ? "Reads LinkedIn, paced" : "Nothing is read from LinkedIn") : s.note}</span>
                {s.available && s.note && <span className="block text-xs text-muted-foreground">{s.note}</span>}
              </button>
            ))}
          </div>
        )}

        {source && !collection?.preview && !collection?.needsMapping && (
          <div className="grid gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">{source.label}</h3>
              <Button size="sm" variant="ghost" onClick={reset}>Change source</Button>
            </div>
            <p className="text-sm text-muted-foreground">{HINTS[source.id]}</p>

            {["post", "urls", "csv", ...URL_SOURCES].includes(source.id) && (
              <Textarea aria-label="Links or data" rows={source.id === "urls" || source.id === "csv" || source.id === "post" ? 5 : 2} value={text} onChange={(e) => setText(e.target.value)} placeholder={PLACEHOLDER[source.id] ?? "https://www.linkedin.com/…"} />
            )}
            {source.id === "csv" && (
              <input
                type="file"
                accept=".csv,text/csv"
                aria-label="CSV file"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  if (file.size >= 5_000_000) setError("That file is larger than 5 MB. Split it into smaller files.");
                  else {
                    setError(undefined);
                    setText(await file.text());
                  }
                }}
              />
            )}
            {source.id === "csv" && (
              <a className="w-fit text-sm underline underline-offset-2" download="synex-sample-leads.csv"
                href={`data:text/csv;charset=utf-8,${encodeURIComponent("linkedin_url,first_name,last_name,company,headline,location,email\nhttps://www.linkedin.com/in/example,Ada,Lovelace,Analytical Engines,Engineer,London,ada@example.com\n")}`}>
                Download a sample CSV
              </a>
            )}
            {source.id === "post" && (
              <fieldset className="grid gap-2 text-sm">
                <legend className="font-medium">Reaction types (none ticked = all)</legend>
                <div className="flex flex-wrap gap-3">
                  {["like", "celebrate", "support", "love", "insightful", "funny"].map((r) => (
                    <label key={r} className="flex items-center gap-2 capitalize">
                      <Checkbox checked={reactions.includes(r)} onCheckedChange={() => setReactions(toggle(reactions, r))} /> {r}
                    </label>
                  ))}
                </div>
                <label className="flex items-center gap-2">
                  <Checkbox checked={comments} onCheckedChange={(v) => setComments(v === true)} /> Also people who commented
                </label>
              </fieldset>
            )}
            {source.id === "connections" && (
              <div className="grid gap-3 sm:grid-cols-3">
                {(["title", "company", "location"] as const).map((k) => (
                  <div key={k} className="grid gap-1">
                    <Label htmlFor={`f-${k}`} className="capitalize">{k}</Label>
                    <Input id={`f-${k}`} value={filters[k]} onChange={(e) => setFilters({ ...filters, [k]: e.target.value })} />
                  </div>
                ))}
              </div>
            )}
            {source.id === "lists" && (
              <div className="grid gap-2 text-sm">
                {(lists.data ?? []).map((l) => (
                  <label key={l.id} className="flex items-center gap-2">
                    <Checkbox checked={listIds.includes(l.id)} onCheckedChange={() => setListIds(toggle(listIds, l.id))} /> {l.name} ({l.leadCount})
                  </label>
                ))}
                {lists.data?.length === 0 && <p className="text-muted-foreground">You have no lists yet.</p>}
              </div>
            )}

            {source.readsLinkedin && (
              <div className="grid gap-1">
                <Label htmlFor="al-sender">Sender account (reads LinkedIn)</Label>
                <NativeSelect id="al-sender" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  {connected.length === 0 && <option value="">No connected account</option>}
                  {connected.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </NativeSelect>
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor="al-name">List name</Label>
                <Input id="al-name" value={listName} onChange={(e) => setListName(e.target.value)} />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="al-limit">How many (up to {source.maxLeads})</Label>
                <Input id="al-limit" type="number" min={1} max={source.maxLeads ?? 1000} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(source.maxLeads ?? 1000, Number(e.target.value) || 1)))} />
              </div>
            </div>
            {source.readsLinkedin && (
              <p className="text-sm text-muted-foreground" data-testid="estimate">
                {estimate.data
                  ? `Estimate: up to ${estimate.data.people} ${companies ? "companies" : "people"}, about ${estimate.data.pages} page loads, around ${estimate.data.minutes} minutes. One run reads at most ${estimate.data.maxPagesPerRun} pages; run it again for more. ${estimate.data.pagesLeftToday === null ? "" : estimate.data.pagesLeftToday === 0 ? "This account has no page reads left today, so the run waits until tomorrow. " : `This account can read ${estimate.data.pagesLeftToday} more pages today. `}`
                  : "Estimating. "}
                Paced with random pauses and counted against this account&apos;s daily reading limit.
              </p>
            )}
            {!companies && <Options skip={skip} setSkip={setSkip} degrees={degrees} setDegrees={setDegrees} showDegrees={source.readsLinkedin} />}
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end">
              <Button loading={busy} onClick={preview} disabled={source.readsLinkedin && !accountId}>Preview</Button>
            </div>
          </div>
        )}

        {source && collection?.needsMapping && mapping && (
          <div className="grid gap-3">
            <p className="text-sm">Which column holds what? ({collection.needsMapping.rows} rows)</p>
            {MAPPING_FIELDS.map(([field, label]) => (
              <div key={field} className="grid gap-1 sm:grid-cols-2 sm:items-center">
                <Label htmlFor={`m-${field}`}>{label}</Label>
                <NativeSelect id={`m-${field}`} value={mapping[field] ?? ""} onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}>
                  <option value="">Not used</option>
                  {collection.needsMapping!.headers.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </NativeSelect>
              </div>
            ))}
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setCollection(null)}>Back</Button>
              <Button loading={busy} onClick={() => { setCollection(null); void preview(); }} disabled={!mapping.linkedin_url}>Preview</Button>
            </div>
          </div>
        )}

        {source && collection && !collection.needsMapping && (collection.preview || working) && (
          <div className="grid gap-3" aria-live="polite">
            <p className="text-sm font-medium">
              {collection.status === "previewing" && "Reading the first results…"}
              {collection.status === "preview_ready" && `Preview: ${collection.preview?.total ?? 0} people found so far`}
              {collection.status === "queued" && "Waiting for the worker…"}
              {collection.status === "running" && `Collecting: ${collection.fetched} found`}
              {collection.status === "completed" && `Done: ${collection.created} leads added to “${collection.listName}”`}
              {collection.status === "stopped" && "Stopped"}
              {collection.status === "failed" && "The read stopped early"}
            </p>
            {collection.detail && <p className="text-sm text-muted-foreground">{collection.detail}</p>}
            {deg && (
              <p className="text-sm text-muted-foreground" data-testid="degree-counts">
                1st: {deg["1"]} · 2nd: {deg["2"]} · 3rd or beyond: {deg["3"]} · unknown: {deg.unknown}
              </p>
            )}
            {people.length > 0 && (
              <ul className="grid gap-1 text-sm" aria-label="First people found">
                {people.map((p) => (
                  <li key={p.profileUrl} className="rounded-sm bg-surface-muted px-3 py-2">
                    <span className="font-medium">{p.name || p.profileUrl}</span> {p.degree ? <span className="text-xs text-muted-foreground">· {p.degree === 3 ? "3rd+" : p.degree === 1 ? "1st" : "2nd"}</span> : null}
                    <span className="block text-xs text-muted-foreground">{[p.headline, p.company, p.location].filter(Boolean).join(" · ")}</span>
                  </li>
                ))}
              </ul>
            )}
            {Object.keys(collection.skipped).length > 0 && (
              <p className="text-sm text-muted-foreground">
                Left out: {Object.entries(collection.skipped).map(([k, n]) => `${n} ${SKIP_LABELS[k] ?? k}`).join(", ")}.
              </p>
            )}
            {collection.status === "preview_ready" && (
              <Options skip={skip} setSkip={setSkip} degrees={degrees} setDegrees={setDegrees} showDegrees />
            )}
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end gap-2">
              {working && <Button variant="outline" onClick={stop}>Stop</Button>}
              {collection.status === "preview_ready" && (
                <>
                  <Button variant="outline" onClick={() => setCollection(null)}>Back</Button>
                  <Button loading={busy} onClick={run}>Add leads</Button>
                </>
              )}
              {["completed", "stopped", "failed"].includes(collection.status) && <Button onClick={() => close(false)}>Close</Button>}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Options({ skip, setSkip, degrees, setDegrees, showDegrees }: {
  skip: { skip_in_campaign: boolean; skip_contacted: boolean; skip_connected: boolean };
  setSkip: (s: { skip_in_campaign: boolean; skip_contacted: boolean; skip_connected: boolean }) => void;
  degrees: number[];
  setDegrees: (d: number[]) => void;
  showDegrees: boolean;
}) {
  const flip = (k: keyof typeof skip) => setSkip({ ...skip, [k]: !skip[k] });
  return (
    <fieldset className="grid gap-2 text-sm">
      <legend className="font-medium">Leave out</legend>
      <label className="flex items-center gap-2"><Checkbox checked={skip.skip_in_campaign} onCheckedChange={() => flip("skip_in_campaign")} /> People already in a campaign</label>
      <label className="flex items-center gap-2"><Checkbox checked={skip.skip_contacted} onCheckedChange={() => flip("skip_contacted")} /> People already contacted</label>
      <label className="flex items-center gap-2"><Checkbox checked={skip.skip_connected} onCheckedChange={() => flip("skip_connected")} /> People already connected</label>
      {showDegrees && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-medium">Connection degree:</span>
          {[1, 2, 3].map((d) => (
            <label key={d} className="flex items-center gap-2">
              <Checkbox checked={degrees.includes(d)} onCheckedChange={() => setDegrees(degrees.includes(d) ? degrees.filter((x) => x !== d) : [...degrees, d].sort())} /> {d === 1 ? "1st" : d === 2 ? "2nd" : "3rd or beyond"}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
