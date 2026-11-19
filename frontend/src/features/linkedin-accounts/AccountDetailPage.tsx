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
      <PageHeader
        title={account.name}
        description={account.headline ?? "No headline"}
        actions={
          <>
            <StatusBadge kind="account" status={account.status} />
            <Button size="sm" variant="secondary" loading={actions.check.isPending} disabled={account.status === "disconnected"} onClick={check}>Resync</Button>
          </>
        }
      />
      <div aria-hidden className="h-20 rounded-lg bg-gradient-to-r from-primary to-primary-soft" />
      <div className="-mt-10 flex items-center gap-3 px-4">
        <UserAvatar name={account.name} src={account.avatarUrl} className="size-16 ring-4 ring-background" />
        <div className="min-w-0 text-sm text-muted-foreground">
          {(account.company || account.location) && (
            <p data-testid="account-place" className="mb-1 text-foreground">{[account.company, account.location].filter(Boolean).join(" · ")}</p>
          )}
          <p>
          {account.profileUrl && <a className="underline-offset-2 hover:underline" href={account.profileUrl} target="_blank" rel="noreferrer noopener">View LinkedIn profile</a>}
          {account.profileUrl && " · "}
          {account.connectedAt ? `Connected since ${formatDate(account.connectedAt, "PP")}` : "Not connected yet"}
          </p>
        </div>
      </div>
      <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-3">
        <div><dt className="text-muted-foreground">Active campaigns</dt><dd className="font-medium">{data.activeCampaigns}</dd></div>
        <div><dt className="text-muted-foreground">Last check</dt><dd className="font-medium">{account.lastCheckedAt ? formatRelative(account.lastCheckedAt) : "Never"}</dd></div>
        <div><dt className="text-muted-foreground">Proxy</dt><dd className="font-medium">{account.proxyConfigured ? "Set" : "None"}</dd></div>
      </dl>
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
