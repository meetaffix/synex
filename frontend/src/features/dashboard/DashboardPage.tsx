import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { useAuth } from "@/features/auth/AuthContext";
import { useCampaignList } from "@/features/campaigns/hooks";
import type { Campaign } from "@/features/campaigns/service";
import { useConversationList } from "@/features/inbox/hooks";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { OnboardingChecklist } from "@/features/onboarding/OnboardingChecklist";
import { AccountTable } from "./AccountTable";
import { ActivityFeed, AttentionPanel } from "./AttentionPanel";
import { HeroMetric } from "./HeroMetric";
import { greetingFor, pointsOf, replyRates, valuesOf } from "./insights";
import { useAccountStats, useSummary, useTimeseries } from "./hooks";
import { MetricCards, noMetrics, type MetricValues } from "./MetricCards";
import { PerformanceChart } from "./PerformanceChart";
import type { DashboardFilters, DateRange, Granularity, Summary } from "./service";

const RANGES: { value: DateRange; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

/** Prefer the dashboard feed. Without it, all-time totals can come from campaigns; nothing else is guessed. */
function metrics(summary: Summary | undefined, campaigns: Campaign[] | undefined, filters: DashboardFilters): { values: MetricValues; source: string } {
  if (summary) {
    return {
      values: { ...summary },
      source: "Figures for the selected filters.",
    };
  }
  if (filters.range === "all" && !filters.accountId && campaigns) {
    const chosen = filters.campaignId ? campaigns.filter((c) => c.id === filters.campaignId) : campaigns;
    const sum = (pick: (c: Campaign) => number) => chosen.reduce((total, c) => total + pick(c), 0);
    return {
      values: {
        ...noMetrics,
        connectionsAccepted: sum((c) => c.stats.connected),
        leadsContacted: sum((c) => c.stats.invitesSent),
        replies: sum((c) => c.stats.replied),
        interestedLeads: sum((c) => c.stats.interested),
      },
      source: "All-time totals from your campaigns. Answer counts and response times need a dashboard feed that is not available yet.",
    };
  }
  return { values: noMetrics, source: "Figures for a date range or a single account need a dashboard feed that is not available yet." };
}

/** One honest line about today, from data Synex already has: actions sent today and replies waiting. */
function todayLine(actions: number, waiting: number): string {
  const sent = actions === 1 ? "1 action sent today" : `${actions} actions sent today`;
  if (actions === 0 && waiting === 0) return "Nothing sent yet today, and no replies are waiting.";
  return `${sent}, ${waiting === 1 ? "1 reply waiting" : `${waiting} replies waiting`}.`;
}

export function DashboardPage() {
  const { user } = useAuth();
  const accounts = useSenderAccounts();
  const campaigns = useCampaignList();
  const conversations = useConversationList({ search: "", status: "all" });
  const [filters, setFilters] = useState<DashboardFilters>({ range: "all", campaignId: "", accountId: "" });
  const [granularity, setGranularity] = useState<Granularity>("week");
  const summary = useSummary(filters);
  const series = useTimeseries(filters, granularity);
  const stats = useAccountStats(filters);

  const first = (user?.fullName ?? "").split(" ")[0];
  const actionsToday = (accounts.data ?? []).reduce((total, account) => total + account.dailyActionsUsed, 0);
  const waiting = (conversations.data ?? []).filter((conversation) => conversation.unread).length;
  const header = (
    <PageHeader
      title={first ? `${greetingFor(new Date())}, ${first}` : greetingFor(new Date())}
      description={accounts.data ? todayLine(actionsToday, waiting) : "How your outreach is performing across sender accounts."}
    />
  );

  if (accounts.isLoading) {
    return (
      <div className="grid gap-6">
        {header}
        <div role="status" aria-label="Loading the dashboard" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((card) => (
            <Skeleton key={card} className="h-28 w-full rounded-lg" />
          ))}
        </div>
      </div>
    );
  }
  if (accounts.isError) {
    return (
      <div className="grid gap-6">
        {header}
        <div role="alert" className="flex flex-col gap-3 rounded-lg bg-danger-soft p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-danger">The dashboard could not be loaded. {requestFailureMessage(accounts.error)}</p>
          <Button size="sm" variant="secondary" onClick={() => void accounts.refetch()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  if (accounts.data?.length === 0) {
    return (
      <div className="grid gap-6">
        {header}
        <OnboardingChecklist />
      </div>
    );
  }

  const readySummary = summary.data?.state === "ready" ? summary.data.data : undefined;
  const { values, source } = metrics(readySummary, campaigns.data, filters);
  const points = pointsOf(series.data);
  const trend = { requests: valuesOf(points, "requests"), accepted: valuesOf(points, "accepted"), replies: valuesOf(points, "replies") };
  const set = (change: Partial<DashboardFilters>) => setFilters((current) => ({ ...current, ...change }));
  const unit = granularity === "week" ? "weekly" : "daily";

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      {header}
      <OnboardingChecklist />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <HeroMetric replies={values.replies} contacted={values.leadsContacted} rates={replyRates(points)} unit={unit} loading={summary.isLoading || campaigns.isLoading} />
        <AttentionPanel conversations={conversations.data ?? []} accounts={accounts.data ?? []} campaigns={campaigns.data ?? []} />
      </div>
      <form aria-label="Filters" className="grid gap-4 sm:grid-cols-3" onSubmit={(event) => event.preventDefault()}>
        <div className="grid gap-2">
          <Label htmlFor="filter-range">Date range</Label>
          <NativeSelect id="filter-range" value={filters.range} onChange={(event) => set({ range: event.target.value as DateRange })}>
            {RANGES.map((range) => (
              <option key={range.value} value={range.value}>
                {range.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="filter-campaign">Campaign</Label>
          <NativeSelect id="filter-campaign" value={filters.campaignId} onChange={(event) => set({ campaignId: event.target.value })}>
            <option value="">All campaigns</option>
            {campaigns.data?.map((campaign) => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="filter-account">Sender account</Label>
          <NativeSelect id="filter-account" value={filters.accountId} onChange={(event) => set({ accountId: event.target.value })}>
            <option value="">All sender accounts</option>
            {accounts.data?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      </form>
      {campaigns.isError && (
        <p role="alert" className="text-sm text-danger">
          Campaign totals could not be loaded. {requestFailureMessage(campaigns.error)}
        </p>
      )}
      {summary.isError && (
        <p role="alert" className="text-sm text-danger">
          Figures for these filters could not be loaded. {requestFailureMessage(summary.error)}
        </p>
      )}
      <MetricCards values={values} loading={summary.isLoading || campaigns.isLoading} source={source} series={trend} unit={unit} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <PerformanceChart
          loading={series.isLoading}
          error={series.isError ? requestFailureMessage(series.error) : undefined}
          feed={series.data}
          granularity={granularity}
          onGranularity={setGranularity}
        />
        <ActivityFeed conversations={conversations.data ?? []} />
      </div>
      <AccountTable accounts={accounts.data ?? []} campaigns={campaigns.data ?? []} stats={stats.data} />
    </div>
  );
}
