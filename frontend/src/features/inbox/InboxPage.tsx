import { useDeferredValue, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Download, Filter, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ConnectAccountEmpty } from "@/components/shared/ConnectAccountEmpty";
import { PageHeader } from "@/components/shared/PageHeader";
import { formatRelative } from "@/utils/format";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { ConversationList, ConversationListLoading, ListMessage } from "./ConversationList";
import { FilterPanel } from "./FilterPanel";
import { ProfilePanel } from "./ProfilePanel";
import { ThreadView } from "./ThreadView";
import { INTEREST_LABEL, emptyFilter, exportCsv, useInboxActions, useInboxList, useInboxMeta, type InboxFilter, type InboxItem } from "./model";

export function InboxPage() {
  const accounts = useSenderAccounts();
  const meta = useInboxMeta();
  const actions = useInboxActions();
  const [filter, setFilter] = useState<InboxFilter>(emptyFilter);
  const [showFilters, setShowFilters] = useState(false);
  const [showProfile, setShowProfile] = useState(true);
  // A link such as /inbox?conversation=<id> (from the dashboard) opens that conversation.
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(() => params.get("conversation"));
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [tag, setTag] = useState("");
  const query = useInboxList({ ...filter, q: useDeferredValue(filter.q) });
  const items: InboxItem[] = query.data?.items ?? [];
  const selected = items.find((c) => c.id === selectedId) ?? null;
  const filtering = JSON.stringify({ ...filter, q: filter.q }) !== JSON.stringify(emptyFilter());
  const lastSynced = useMemo(() => {
    const times = (meta.data?.accounts ?? []).map((a) => a.lastSyncedAt).filter((t): t is string => !!t).sort();
    return times.at(-1) ?? null;
  }, [meta.data]);

  if (accounts.isSuccess && accounts.data.length === 0) {
    return (
      <div className="grid gap-6">
        <PageHeader title="Inbox" />
        <ConnectAccountEmpty title="Connect LinkedIn account to receive replies" description="Replies from your leads will appear here." />
      </div>
    );
  }

  const bulk = (action: Parameters<typeof actions.bulk.mutate>[0]["action"], value?: string) =>
    actions.bulk.mutate({ ids: [...checked], action, value }, { onSuccess: () => { toast.success("Updated."); setChecked(new Set()); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const refresh = () =>
    actions.refreshSenders.mutate(filter.accounts, {
      onSuccess: (r) => toast.success(r.queued ? `Reading ${r.queued} inbox${r.queued === 1 ? "" : "es"}. New messages appear in a moment.` : `Nothing to read: ${r.skipped.map((s) => `${s.account} (${s.reason})`).join(", ") || "no senders"}.`),
      onError: (e) => toast.error(requestFailureMessage(e)),
    });
  const download = async () => {
    try {
      const url = URL.createObjectURL(new Blob([await exportCsv(filter)], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "synex-inbox.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(requestFailureMessage(error));
    }
  };

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Inbox"
        description="The central inbox for all your LinkedIn accounts."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <span role="status" className="text-xs text-muted-foreground">{lastSynced ? `Last read ${formatRelative(lastSynced)}` : "Not read yet"}</span>
            <Button size="sm" variant="outline" loading={actions.refreshSenders.isPending} onClick={refresh}><RefreshCw aria-hidden /> Refresh</Button>
            <Button size="sm" variant="outline" disabled={!query.data?.total} onClick={() => void download()}><Download aria-hidden /> Export CSV</Button>
          </div>
        }
      />
      <div role="group" aria-label="Sender accounts" className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={filter.accounts.length === 0 ? "default" : "outline"} aria-pressed={filter.accounts.length === 0} onClick={() => setFilter({ ...filter, accounts: [] })}>All accounts</Button>
        {(meta.data?.accounts ?? []).map((a) => (
          <Button key={a.id} size="sm" variant={filter.accounts.includes(a.id) ? "default" : "outline"} aria-pressed={filter.accounts.includes(a.id)}
            onClick={() => setFilter({ ...filter, accounts: filter.accounts.includes(a.id) ? filter.accounts.filter((x) => x !== a.id) : [...filter.accounts, a.id] })}>{a.name}</Button>
        ))}
        <Button asChild size="sm" variant="ghost"><Link to="/linkedin-accounts?connect=1">Add</Link></Button>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] overflow-hidden rounded-lg border border-border bg-surface shadow-raised lg:min-h-[34rem] lg:grid-cols-[22rem_minmax(0,1fr)] xl:grid-cols-[22rem_minmax(0,1fr)_20rem]">
        <section aria-label="Conversation list" className={selected ? "hidden border-border lg:block lg:border-r" : "border-border lg:border-r"}>
          <div className="grid gap-3 border-b border-border p-4">
            <div className="grid gap-2">
              <Label htmlFor="inbox-search">Search all conversations</Label>
              <Input id="inbox-search" type="search" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} placeholder="Name, company or message" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" aria-expanded={showFilters} onClick={() => setShowFilters(!showFilters)}><Filter aria-hidden /> Filters</Button>
              {filtering && <Button size="sm" variant="ghost" onClick={() => setFilter(emptyFilter())}>Clear filters</Button>}
              <span className="ml-auto self-center text-xs text-muted-foreground">{query.data ? `${query.data.total} conversation${query.data.total === 1 ? "" : "s"}` : ""}</span>
            </div>
          </div>
          {showFilters && <FilterPanel value={filter} onChange={setFilter} />}
          {checked.size > 0 && (
            <div role="toolbar" aria-label="Bulk actions" className="grid gap-2 border-b border-border bg-surface-muted p-3 text-sm">
              <span className="font-medium">{checked.size} selected</span>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => bulk("read")}>Mark read</Button>
                <Button size="sm" variant="outline" onClick={() => bulk("unread")}>Mark unread</Button>
                <Button size="sm" variant="outline" onClick={() => bulk("star")}>Star</Button>
                <Button size="sm" variant="outline" onClick={() => bulk(filter.archived ? "unarchive" : "archive")}>{filter.archived ? "Unarchive" : "Archive"}</Button>
                <NativeSelect aria-label="Set interest for the selected" className="w-auto" value="" onChange={(e) => e.target.value && bulk("interest", e.target.value)}>
                  <option value="">Set interest</option>
                  {Object.entries(INTEREST_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                </NativeSelect>
              </div>
              <div className="flex gap-2">
                <Input aria-label="Tag for the selected" value={tag} maxLength={40} placeholder="Tag" onChange={(e) => setTag(e.target.value)} />
                <Button size="sm" variant="outline" disabled={!tag.trim()} onClick={() => { bulk("tag_add", tag.trim()); setTag(""); }}>Add tag</Button>
                <Button size="sm" variant="ghost" onClick={() => setChecked(new Set())}>Clear</Button>
              </div>
            </div>
          )}
          {query.isLoading && <ConversationListLoading />}
          {query.isError && !query.data && <ListMessage title="Conversations could not be loaded" action={{ label: "Try again", onClick: () => void query.refetch() }}>{requestFailureMessage(query.error)}</ListMessage>}
          {query.data && items.length === 0 && filtering && <ListMessage title="No conversations match" action={{ label: "Clear filters", onClick: () => setFilter(emptyFilter()) }}>Try different filters, or show everything.</ListMessage>}
          {query.data && items.length === 0 && !filtering && (
            <div className="grid justify-items-center gap-3 p-6 text-center">
              <Illustration name="inbox" className="h-24" />
              <p className="text-sm font-medium">No conversations yet</p>
              <p className="text-sm text-muted-foreground">Conversations appear here once a lead replies to a campaign message, or after Refresh reads your inboxes.</p>
              {(meta.data?.accounts ?? []).filter((a) => a.live && a.syncMode === "synex_only").map((a) => (
                <p key={a.id} role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-left text-sm">
                  {a.name} keeps only conversations with people Synex has contacted{a.lastSkipped > 0 ? `, so ${a.lastSkipped} other ${a.lastSkipped === 1 ? "conversation" : "conversations"} on LinkedIn ${a.lastSkipped === 1 ? "is" : "are"} not shown` : ""}.
                  {" "}To see all your LinkedIn chats here, <Link className="underline underline-offset-2" to={`/linkedin-accounts/${a.id}`}>change its conversation sync</Link> to all conversations.
                </p>
              ))}
              <Button asChild size="sm" variant="secondary"><Link to="/campaigns">View campaigns</Link></Button>
            </div>
          )}
          {items.length > 0 && (
            <ConversationList conversations={items} selectedId={selectedId} checked={checked}
              onSelect={(id) => { setSelectedId(id); const c = items.find((x) => x.id === id); if (c?.unread) actions.bulk.mutate({ ids: [id], action: "read" }); }}
              onCheck={(id, on) => setChecked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; })}
              onStar={(c) => actions.bulk.mutate({ ids: [c.id], action: c.starred ? "unstar" : "star" })} />
          )}
        </section>
        <section aria-label="Conversation" className={selected ? "" : "hidden lg:block"}>
          {selected ? (
            <ThreadView key={selected.id} conversation={selected} onBack={() => setSelectedId(null)} />
          ) : (
            <div className="grid h-full place-items-center content-center gap-3 p-8 text-center">
              <Illustration name="inbox" />
              <p className="max-w-xs text-sm text-muted-foreground">Select a conversation</p>
            </div>
          )}
        </section>
        {selected && showProfile && <ProfilePanel item={selected} onClose={() => setShowProfile(false)} />}
        {selected && !showProfile && <div className="hidden p-3 xl:block"><Button size="sm" variant="outline" onClick={() => setShowProfile(true)}>Show profile details</Button></div>}
      </div>
    </div>
  );
}
