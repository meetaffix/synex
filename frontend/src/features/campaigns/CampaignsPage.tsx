import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ComingNext } from "@/components/shared/ComingNext";
import { EmptyState } from "@/components/shared/EmptyState";
import { ConnectAccountEmpty } from "@/components/shared/ConnectAccountEmpty";
import { PageHeader } from "@/components/shared/PageHeader";
import { AvatarStack } from "@/components/ui/avatar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { SortableHead, Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { useSort } from "@/hooks/useSort";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { formatNumber, formatPercent } from "@/utils/format";
import { campaignAccountIds, type Campaign } from "./service";
import { useCampaignList } from "./hooks";

const NEW_CAMPAIGN = (
  <ComingNext label="Building campaigns comes next">
    <Button disabled>New campaign</Button>
  </ComingNext>
);

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
        actions={!loading && !failure && (accounts.data?.length === 0 || campaigns.data?.length === 0) ? undefined : NEW_CAMPAIGN}
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
          title="Connect a sender account to run campaigns"
          description="A campaign sends connection requests and messages from a LinkedIn profile you connect to Synex. Connect one first, then your campaigns appear here."
        />
      )}
      {!loading && !failure && !!accounts.data?.length && campaigns.data?.length === 0 && (
        <EmptyState
          illustration="campaigns"
          title="No campaigns yet"
          description="A campaign is a sequence of steps, such as a connection request followed by a message, that Synex runs for each lead in a list. Building campaigns in the app is coming next; existing campaigns show here with their results."
          action={NEW_CAMPAIGN}
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
  status: (row: CampaignRow) => row.campaign.status,
  progress: (row: CampaignRow) => (row.campaign.stats.totalLeads ? row.campaign.stats.invitesSent / row.campaign.stats.totalLeads : 0),
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

/** Leads contacted out of the leads in the campaign, as a bar and in words. */
function Progress({ contacted, total }: { contacted: number; total: number }) {
  const percent = total > 0 ? Math.min(100, (contacted / total) * 100) : 0;
  return (
    <span className="grid min-w-[9rem] gap-1.5">
      <span className="text-sm">
        {formatNumber(contacted)} of {formatNumber(total)} contacted
      </span>
      <span role="progressbar" aria-label="Leads contacted" aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(contacted, total)} className="h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <span className="block h-full rounded-full bg-primary transition-[width] duration-700 motion-reduce:transition-none" style={{ width: `${percent}%` }} />
      </span>
    </span>
  );
}

function CampaignTable({ campaigns, accountNames }: { campaigns: Campaign[]; accountNames: Map<string, string> }) {
  const rows = campaigns.map((campaign) => {
    const names = campaignAccountIds(campaign).map((id) => accountNames.get(id)).filter((name): name is string => !!name);
    return {
      campaign,
      accounts: names.length ? names.join(", ") : campaign.accountName || "None",
      people: (names.length ? names : campaign.accountName ? [campaign.accountName] : []).map((name) => ({ name })),
    };
  });
  const { sorted, sort, toggle } = useSort(rows, CAMPAIGN_SORT, { key: "name", direction: "asc" });
  const head = (key: CampaignSort, label: string, align?: "right") => (
    <SortableHead label={label} active={sort.key === key} direction={sort.direction} onSort={() => toggle(key)} align={align} />
  );
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface shadow-raised">
      <Table regionLabel="Campaigns table" className="min-w-[56rem]">
        <caption className="sr-only">Campaigns and their results</caption>
        <TableHeader>
          <TableRow>
            {head("name", "Name")}
            {head("status", "Status")}
            {head("progress", "Progress")}
            {head("accounts", "Sender accounts")}
            {head("leads", "Leads", "right")}
            {head("accepted", "Accepted %", "right")}
            {head("replies", "Reply %", "right")}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map(({ campaign, accounts, people }) => (
            <TableRow key={campaign.id}>
              <th scope="row" className="h-14 px-4 py-2 text-left font-medium">{campaign.name}</th>
              <TableCell><StatusBadge kind="campaign" status={campaign.status} /></TableCell>
              <TableCell>
                <Progress contacted={campaign.stats.invitesSent} total={campaign.stats.totalLeads} />
              </TableCell>
              <TableCell>
                {people.length > 0 ? (
                  <span className="flex items-center gap-3">
                    <AvatarStack people={people} />
                    <span className="max-w-[12rem] truncate text-muted-foreground">{accounts}</span>
                  </span>
                ) : (
                  "None"
                )}
              </TableCell>
              <TableCell className="text-right">{formatNumber(campaign.stats.totalLeads)}</TableCell>
              <TableCell className="text-right">{formatPercent(campaign.stats.acceptanceRate, 0)}</TableCell>
              <TableCell className="text-right">{formatPercent(campaign.stats.replyRate, 0)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
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
