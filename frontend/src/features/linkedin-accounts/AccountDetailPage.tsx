import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "@/services/client";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { UserAvatar } from "@/components/ui/avatar";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TabPanel, Tabs, type TabItem } from "@/components/ui/tabs";
import { formatDate, formatRelative } from "@/utils/format";
import { requestFailureMessage } from "./copy";
import { useAccountActions, useSenderAccounts } from "./hooks";
import { useAccountDetails } from "./management";
import { ConnectionsTab } from "./tabs/ConnectionsTab";
import { AiConfigTab } from "./tabs/AiConfigTab";
import { SenderLimitsTab } from "./tabs/SenderLimitsTab";
import { AccountTab, HealthTab, PrivacyTab } from "./tabs/SettingsTabs";

const TABS: TabItem[] = [
  { id: "limits", label: "Sender limits" },
  { id: "privacy", label: "Inbox privacy" },
  { id: "health", label: "Health" },
  { id: "connections", label: "Manage connections" },
  { id: "ai", label: "AI configuration" },
  { id: "account", label: "Account" },
];

/** One sender account: its limits, privacy, health and lifecycle. */
export function AccountDetailPage() {
  const { accountId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const accounts = useSenderAccounts();
  const details = useAccountDetails(accountId);
  const actions = useAccountActions();
  const account = accounts.data?.find((item) => item.id === accountId);
  const requested = params.get("tab") ?? "limits";
  const tab = TABS.some((item) => item.id === requested) ? requested : "limits";

  const back = (
    <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit">
      <Link to="/linkedin-accounts">
        <ArrowLeft aria-hidden /> All sender accounts
      </Link>
    </Button>
  );

  if (accounts.isLoading || details.isLoading) {
    return (
      <div className="grid gap-6" aria-busy="true">
        {back}
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-64 w-full" />
        <p role="status" className="sr-only">Loading this account.</p>
      </div>
    );
  }
  if (!account || details.isError || !details.data) {
    return (
      <div className="grid gap-4">
        {back}
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          {details.isError && !(details.error instanceof ApiError && details.error.status === 404)
            ? requestFailureMessage(details.error)
            : "This sender account was not found. It may have been removed."}
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={() => void details.refetch()}>Try again</Button>
          </div>
        </div>
      </div>
    );
  }

  const data = details.data;
  const check = () =>
    actions.check.mutate(account.id, {
      onSuccess: (checked) => toast.success(`${checked.name} checked: ${checked.status.replaceAll("_", " ")}.`),
      onError: (error) => toast.error(requestFailureMessage(error)),
    });

  return (
    <div className="grid grid-cols-1 gap-6">
      {back}
      <header className="flex flex-wrap items-center gap-4">
        <UserAvatar name={account.name} src={account.avatarUrl} className="size-14" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{account.name}</h1>
          <p className="truncate text-sm text-muted-foreground">{account.headline ?? "No headline"}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {(account.company || account.location) && <span data-testid="account-place" className="text-foreground">{[account.company, account.location].filter(Boolean).join(" · ")}</span>}
            <span>{account.connectedAt ? `Connected since ${formatDate(account.connectedAt, "PP")}` : "Not connected yet"}</span>
            <span>{data.activeCampaigns} active campaign{data.activeCampaigns === 1 ? "" : "s"}</span>
            <span>Checked {account.lastCheckedAt ? formatRelative(account.lastCheckedAt) : "never"}</span>
            {account.profileUrl && <a className="text-primary-ink underline-offset-2 hover:underline" href={account.profileUrl} target="_blank" rel="noreferrer noopener">LinkedIn profile</a>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge kind="account" status={account.status} />
          <Button size="sm" variant="secondary" loading={actions.check.isPending} disabled={account.status === "disconnected"} onClick={check}>Resync</Button>
        </div>
      </header>
      <div className="min-w-0">
        <Tabs label="Account sections" tabs={TABS} value={tab} idPrefix="acct" onChange={(next) => setParams({ tab: next }, { replace: true })} />
        <TabPanel id="limits" active={tab === "limits"} idPrefix="acct"><SenderLimitsTab accountId={account.id} details={data} /></TabPanel>
        <TabPanel id="privacy" active={tab === "privacy"} idPrefix="acct"><PrivacyTab account={account} details={data} /></TabPanel>
        <TabPanel id="health" active={tab === "health"} idPrefix="acct"><HealthTab account={account} details={data} /></TabPanel>
        <TabPanel id="connections" active={tab === "connections"} idPrefix="acct"><ConnectionsTab accountId={account.id} disabled={account.status === "disconnected" || data.lifecycle === "deactivated"} /></TabPanel>
        <TabPanel id="ai" active={tab === "ai"} idPrefix="acct"><AiConfigTab accountId={account.id} details={data} /></TabPanel>
        <TabPanel id="account" active={tab === "account"} idPrefix="acct"><AccountTab account={account} details={data} /></TabPanel>
      </div>
    </div>
  );
}
