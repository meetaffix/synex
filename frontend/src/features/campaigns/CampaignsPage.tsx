import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { ConnectAccountEmpty } from "@/components/shared/ConnectAccountEmpty";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { AvatarStack } from "@/components/ui/avatar";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { SortableHead, Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { useSort } from "@/hooks/useSort";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { api } from "@/services/client";
import { formatNumber, formatPercent } from "@/utils/format";
import { campaignAccountIds, type Campaign } from "./service";
import { useCampaignList } from "./hooks";

function ImportSequence() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const run = useMutation({
    mutationFn: async (file: File) => {
      let sequence: unknown;
      try {
        sequence = JSON.parse(await file.text());
      } catch {
        throw new Error("That file could not be read. Use a .synex-sequence.json file made with Share sequence.");
      }
      return api.post<{ id: string }>("/campaigns", { action: "import", sequence });
    },
    onSuccess: async (made) => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Sequence imported as a draft."); navigate(`/campaigns/${made.id}/edit?step=2`); },
    onError: (e) => toast.error(e instanceof Error && e.message ? e.message : requestFailureMessage(e)),
  });
  return (
    <>
      <Button variant="outline" loading={run.isPending} onClick={() => document.getElementById("import-sequence")?.click()}>Import sequence</Button>
      <input id="import-sequence" type="file" accept=".json,application/json" className="sr-only" tabIndex={-1} aria-label="Import a sequence file"
        onChange={(e) => { const f = e.target.files?.[0]; if (f && f.size < 1_000_000) run.mutate(f); e.target.value = ""; }} />
    </>
  );
}

const NEW_CAMPAIGN = (
  <div className="flex flex-wrap gap-2">
    <ImportSequence />
    <Button asChild>
      <Link to="/campaigns/new">New campaign</Link>
    </Button>
  </div>
);

const STATUS: Record<string, { label: string; variant: NonNullable<BadgeProps["variant"]> }> = {
  draft: { label: "Draft", variant: "muted" },
  paused: { label: "Paused", variant: "warning" },
  queued: { label: "Queued", variant: "default" },
  running: { label: "Running", variant: "success" },
  no_more_pending: { label: "No more pending actions", variant: "secondary" },
  finished: { label: "Finished", variant: "secondary" },
  failed: { label: "Failed", variant: "destructive" },
  archived: { label: "Archived", variant: "muted" },
};
const FILTERS = ["draft", "paused", "queued", "running", "no_more_pending", "finished", "failed", "archived"] as const;

export function CampaignsPage() {
  const accounts = useSenderAccounts();
  const campaigns = useCampaignList();
  const loading = accounts.isLoading || campaigns.isLoading;
  const failure = accounts.error ?? campaigns.error;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      {/* One primary action per view: while an empty state is showing, it carries the action. */}
      <PageHeader
        title="Campaigns"
        description="Sequences that contact leads from your sender accounts."
        actions={!loading && !failure && accounts.data?.length !== 0 && campaigns.data?.length === 0 ? undefined : NEW_CAMPAIGN}
      />
      {loading && <LoadingTable />}
      {!loading && failure && (
        <div role="alert" className="flex flex-col gap-3 rounded-lg bg-danger-soft p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-danger">Campaigns could not be loaded. {requestFailureMessage(failure)}</p>
          <Button size="sm" variant="outline" onClick={() => void Promise.all([accounts.refetch(), campaigns.refetch()])}>
            Try again
          </Button>
        </div>
      )}
      {!loading && !failure && accounts.data?.length === 0 && (
        <ConnectAccountEmpty
          title="Connect LinkedIn account to run campaigns"
          description="A campaign sends connection requests and messages from a LinkedIn profile you connect to Synex. Connect one first, then your campaigns appear here."
        />
      )}
      {!loading && !failure && !!accounts.data?.length && campaigns.data?.length === 0 && (
        <EmptyState
          illustration="campaigns"
          title="Ready to start your first campaign?"
          description="A campaign is a sequence of steps, such as a connection request followed by a message, that Synex runs for each lead in a list. Build one with New campaign; its results show here."
          action={<div className="flex flex-wrap justify-center gap-2"><Button asChild><Link to="/campaigns/new">Create your first campaign</Link></Button><ImportSequence /></div>}
        />
      )}
      {!loading && !failure && !!campaigns.data?.length && (
        <CampaignTable campaigns={campaigns.data} accountNames={new Map((accounts.data ?? []).map((a) => [a.id, a.name]))} />
      )}
    </div>
  );
}

const CAMPAIGN_SORT = {
  name: (row: CampaignRow) => row.campaign.name,
  status: (row: CampaignRow) => row.campaign.displayStatus,
  accounts: (row: CampaignRow) => row.accounts,
  leads: (row: CampaignRow) => row.campaign.stats.totalLeads,
  accepted: (row: CampaignRow) => row.campaign.stats.acceptanceRate,
  replies: (row: CampaignRow) => row.campaign.stats.replyRate,
};
type CampaignSort = keyof typeof CAMPAIGN_SORT;
interface CampaignRow {
  campaign: Campaign;
  accounts: string;
  people: { name: string; src?: string | null }[];
}

function CampaignTable({ campaigns, accountNames }: { campaigns: Campaign[]; accountNames: Map<string, string> }) {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [account, setAccount] = useState("");
  const [deleting, setDeleting] = useState<Campaign | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["campaigns"] });
  const act = useMutation({
    mutationFn: ({ action, id }: { action: "duplicate" | "archive" | "delete"; id: string }) => api.post("/campaigns", { action, id }),
    onSuccess: refresh,
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const share = async (c: Campaign) => {
    try {
      const data = await api.get(`/campaigns/${c.id}/share`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${c.name.replace(/[^A-Za-z0-9]+/g, "-").toLowerCase() || "sequence"}.synex-sequence.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(requestFailureMessage(error));
    }
  };

  const rows = useMemo(
    () =>
      campaigns
        .filter((c) => (status ? c.displayStatus === status : c.displayStatus !== "archived"))
        .filter((c) => c.name.toLowerCase().includes(query.trim().toLowerCase()))
        .filter((c) => !account || campaignAccountIds(c).includes(account))
        .map((campaign) => {
          const names = campaignAccountIds(campaign).map((id) => accountNames.get(id)).filter((name): name is string => !!name);
          return { campaign, accounts: names.length ? names.join(", ") : campaign.accountName || "None", people: (names.length ? names : campaign.accountName ? [campaign.accountName] : []).map((name) => ({ name })) };
        }),
    [campaigns, accountNames, query, status, account],
  );
  const { sorted, sort, toggle } = useSort(rows, CAMPAIGN_SORT, { key: "name", direction: "asc" });
  const head = (key: CampaignSort, label: string, align?: "right") => (
    <SortableHead label={label} active={sort.key === key} direction={sort.direction} onSort={() => toggle(key)} align={align} />
  );
  const used = [...new Set(campaigns.flatMap(campaignAccountIds))];

  return (
    <div className="grid min-w-0 gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-0 gap-1">
          <label htmlFor="campaign-search" className="text-sm font-medium">Search</label>
          <Input id="campaign-search" type="search" placeholder="Campaign name" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="grid gap-1">
          <label htmlFor="campaign-status" className="text-sm font-medium">Status</label>
          <NativeSelect id="campaign-status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {FILTERS.map((f) => <option key={f} value={f}>{STATUS[f].label}</option>)}
          </NativeSelect>
        </div>
        <div className="grid gap-1">
          <label htmlFor="campaign-account" className="text-sm font-medium">Accounts</label>
          <NativeSelect id="campaign-account" value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">All accounts</option>
            {used.map((id) => <option key={id} value={id}>{accountNames.get(id) ?? id}</option>)}
          </NativeSelect>
        </div>
      </div>
      {sorted.length === 0 && <p role="status" className="rounded-lg border border-border p-4 text-sm text-muted-foreground">No campaigns match.</p>}
      {sorted.length > 0 && (
        <div className="min-w-0 rounded-lg border border-border bg-surface shadow-raised">
          <Table regionLabel="Campaigns table" className="min-w-[56rem]">
            <caption className="sr-only">Campaigns and their results</caption>
            <TableHeader>
              <TableRow>
                {head("name", "Name")}
                {head("status", "Status")}
                {head("leads", "Leads", "right")}
                {head("accepted", "Accepted %", "right")}
                {head("replies", "Reply %", "right")}
                {head("accounts", "Accounts")}
                <th scope="col" className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Actions</th>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map(({ campaign, accounts, people }) => {
                const editable = ["draft", "paused"].includes(campaign.status);
                return (
                  <TableRow key={campaign.id}>
                    <th scope="row" className="h-14 px-4 py-2 text-left font-medium">
                      <Link className="underline-offset-2 hover:underline" to={campaign.status === "draft" ? `/campaigns/${campaign.id}/edit` : `/campaigns/${campaign.id}`}>{campaign.name}</Link>
                    </th>
                    <TableCell><Badge variant={(STATUS[campaign.displayStatus] ?? STATUS.draft).variant}>{(STATUS[campaign.displayStatus] ?? { label: campaign.displayStatus }).label}</Badge></TableCell>
                    <TableCell className="text-right">{formatNumber(campaign.stats.totalLeads)}</TableCell>
                    <TableCell className="text-right">{formatPercent(campaign.stats.acceptanceRate, 0)}</TableCell>
                    <TableCell className="text-right">{formatPercent(campaign.stats.replyRate, 0)}</TableCell>
                    <TableCell>
                      {people.length > 0 ? (
                        <span className="flex items-center gap-3"><AvatarStack people={people} /><span className="max-w-[12rem] truncate text-muted-foreground">{accounts}</span></span>
                      ) : "None"}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button size="icon-sm" variant="ghost" aria-label={`More actions for ${campaign.name}`}><MoreHorizontal /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {campaign.status !== "draft" && <DropdownMenuItem asChild><Link to={`/campaigns/${campaign.id}`}>View campaign</Link></DropdownMenuItem>}
                          {editable && <DropdownMenuItem asChild><Link to={`/campaigns/${campaign.id}/edit`}>Edit campaign</Link></DropdownMenuItem>}
                          <DropdownMenuItem onSelect={() => act.mutate({ action: "duplicate", id: campaign.id }, { onSuccess: () => toast.success("Campaign duplicated as a draft.") })}>Duplicate campaign</DropdownMenuItem>
                          <DropdownMenuItem onSelect={() => void share(campaign)}>Share sequence</DropdownMenuItem>
                          <DropdownMenuItem disabled={["draft", "active", "archived"].includes(campaign.status)} onSelect={() => act.mutate({ action: "archive", id: campaign.id }, { onSuccess: () => toast.success("Campaign archived.") })}>Archive campaign</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-danger focus:text-danger" onSelect={() => setDeleting(campaign)}>Delete campaign</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Do you really want to delete ${deleting?.name ?? "this campaign"}?`}
        description="The campaign, its sequence and its prepared messages are removed. Leads and conversations stay. This cannot be undone."
        confirmLabel="Delete campaign"
        destructive
        loading={act.isPending}
        onConfirm={() => deleting && act.mutate({ action: "delete", id: deleting.id }, { onSuccess: () => { toast.success("Campaign deleted."); setDeleting(null); } })}
      />
    </div>
  );
}

function LoadingTable() {
  return (
    <div role="status" aria-label="Loading campaigns" className="grid gap-2 rounded-lg border border-border bg-surface p-4 sm:p-6">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-10 w-full" />
      ))}
    </div>
  );
}
