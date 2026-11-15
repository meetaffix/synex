import { StatusBadge } from "@/components/shared/StatusBadge";
import { SortableHead, Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { useSort } from "@/hooks/useSort";
import { campaignAccountIds, type Campaign } from "@/features/campaigns/service";
import type { SenderAccount } from "@/features/linkedin-accounts/schemas";
import { formatNumber, formatPercent } from "@/utils/format";
import type { AccountStats, Feed } from "./service";

interface Props {
  accounts: SenderAccount[];
  campaigns: Campaign[];
  stats?: Feed<AccountStats>;
}

function Missing() {
  return (
    <>
      <span aria-hidden>—</span>
      <span className="sr-only">Not available yet</span>
    </>
  );
}

interface AccountRow {
  account: SenderAccount;
  used: number;
  row?: { requestsSent: number; acceptedPercent: number; leadsContacted: number; replyPercent: number };
}

const ACCOUNT_SORT = {
  name: (r: AccountRow) => r.account.name,
  status: (r: AccountRow) => r.account.status,
  campaigns: (r: AccountRow) => r.used,
  requests: (r: AccountRow) => r.row?.requestsSent,
  accepted: (r: AccountRow) => r.row?.acceptedPercent,
  contacted: (r: AccountRow) => r.row?.leadsContacted,
  replies: (r: AccountRow) => r.row?.replyPercent,
};

export function AccountTable({ accounts, campaigns, stats }: Props) {
  const byAccount = new Map(stats?.state === "ready" ? stats.data.map((row) => [row.accountId, row]) : []);
  const rows = accounts.map((account) => ({
    account,
    used: campaigns.filter((c) => campaignAccountIds(c).includes(account.id)).length,
    row: byAccount.get(account.id),
  }));
  const { sorted, sort, toggle } = useSort(rows, ACCOUNT_SORT, { key: "name", direction: "asc" });
  const head = (key: keyof typeof ACCOUNT_SORT, label: string, align?: "right") => (
    <SortableHead label={label} active={sort.key === key} direction={sort.direction} onSort={() => toggle(key)} align={align} />
  );
  return (
    <section aria-labelledby="accounts-title" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      <h2 id="accounts-title" className="text-base font-semibold">
        Sender accounts
      </h2>
      <div className="min-w-0 rounded-lg border border-border bg-surface shadow-raised">
        <Table regionLabel="Sender account results" className="min-w-[44rem]">
          <caption className="sr-only">Results for each sender account</caption>
          <TableHeader>
            <TableRow>
              {head("name", "Account")}
              {head("status", "Status")}
              {head("campaigns", "Campaigns", "right")}
              {head("requests", "Requests sent", "right")}
              {head("accepted", "Accepted %", "right")}
              {head("contacted", "Leads contacted", "right")}
              {head("replies", "Reply %", "right")}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map(({ account, used, row }) => (
              <TableRow key={account.id}>
                <th scope="row" className="h-14 px-4 py-2 text-left font-medium">{account.name}</th>
                <TableCell><StatusBadge kind="account" status={account.status} /></TableCell>
                <TableCell className="text-right">{formatNumber(used)}</TableCell>
                <TableCell className="text-right">{row ? formatNumber(row.requestsSent) : <Missing />}</TableCell>
                <TableCell className="text-right">{row ? formatPercent(row.acceptedPercent, 0) : <Missing />}</TableCell>
                <TableCell className="text-right">{row ? formatNumber(row.leadsContacted) : <Missing />}</TableCell>
                <TableCell className="text-right">{row ? formatPercent(row.replyPercent, 0) : <Missing />}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {stats?.state === "unavailable" && (
        <p className="text-xs text-muted-foreground">Per-account results are not available yet. Account, status and campaign counts above are live.</p>
      )}
    </section>
  );
}
