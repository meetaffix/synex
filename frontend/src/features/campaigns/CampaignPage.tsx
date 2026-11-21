import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pause, Pencil, Play } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api, ApiError } from "@/services/client";
import { formatNumber, formatPercent, formatRelative } from "@/utils/format";
import { BuilderPage } from "./builder/BuilderPage";
import { type ServerCampaign } from "./builder/model";

type Detail = ServerCampaign & { displayStatus?: string; accountName?: string; stats?: { totalLeads?: number } };
interface Task { id: string; runId: string; type: string; status: string; leadName: string; error: string | null; updatedAt: string | null }
interface Monitor {
  status: string; health: "ok" | "attention" | "failed"; runCounts: Record<string, number>; currentActions: Task[]; lastExecuted: Task | null; failures: Task[];
  workerRunning?: boolean; waiting?: { code: string; message: string } | null;
  nextScheduled: { leadName: string; at: string } | null; accounts: { id: string; name: string; live: boolean; dailyActionsUsed: number; dailyActionLimit: number }[];
}
interface Run { runId: string; leadName: string; headline: string; status: string; stopReason: string | null; stepType: string | null; nextActionAt: string | null }

const STATUS: Record<string, { label: string; variant: NonNullable<BadgeProps["variant"]> }> = {
  active: { label: "Running", variant: "success" }, paused: { label: "Paused", variant: "warning" }, draft: { label: "Draft", variant: "muted" },
  completed: { label: "Finished", variant: "secondary" }, archived: { label: "Archived", variant: "muted" },
};
const RUN: Record<string, string> = { running: "In progress", waiting_connection: "Waiting to connect", awaiting_agent: "Waiting for the worker", needs_review: "Needs review", completed: "Finished", stopped: "Stopped" };
const STOP: Record<string, string> = { replied: "Replied", interested: "Interested", not_interested: "Not interested", ended: "Sequence ended", send_failed: "Could not send" };
const STEP: Record<string, string> = { connection_request: "Connection request", message: "Message", follow_up: "Follow-up", wait: "Waiting", if_connected: "Waiting for acceptance", profile_visit: "Profile visit", follow: "Follow", like_post: "Like a post", withdraw_invite: "Withdraw invite", voice_note: "Voice note", inmail: "InMail", free_inmail: "Free InMail", end: "End" };
const ACTION: Record<string, string> = { send_invite: "Connection request", send_message: "Message", visit_profile: "Profile visit", sync_inbox: "Inbox read", check_connection: "Connection check" };

const TABS = [{ id: "overview", label: "Overview" }, { id: "leads", label: "Leads" }, { id: "sequence", label: "Sequence" }, { id: "settings", label: "Settings" }];

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-raised">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** What a launched campaign is doing: counts, what is happening now and next, each lead's progress, and Pause. Refreshes by itself. */
export function CampaignPage() {
  const { campaignId = "" } = useParams();
  const qc = useQueryClient();
  const [tab, setTab] = useState("overview");
  const campaign = useQuery({ queryKey: ["campaign-page", campaignId], queryFn: () => api.get<Detail>(`/campaigns?id=${campaignId}`), refetchInterval: 10_000 });
  const monitor = useQuery({ queryKey: ["campaign-monitor", campaignId], queryFn: () => api.get<Monitor>(`/campaigns?id=${campaignId}&monitor=1`), refetchInterval: 10_000 });
  const runs = useQuery({ queryKey: ["campaign-runs", campaignId], queryFn: () => api.get<Run[]>(`/campaigns/${campaignId}/runs`), refetchInterval: 10_000 });
  const refresh = () => Promise.all(["campaign-page", "campaign-monitor", "campaign-runs", "campaigns"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const setStatus = useMutation({
    mutationFn: (status: "paused" | "active") => api.post("/campaigns", { action: "update", id: campaignId, status }),
    onSuccess: async (_d, status) => { await refresh(); toast.success(status === "paused" ? "Campaign paused. Nothing more is sent until you resume it." : "Campaign resumed."); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const fix = useMutation({
    mutationFn: (v: { runId: string; runAction: "retry" | "skip" }) => api.post("/campaigns", { action: "run", id: campaignId, ...v }),
    onSuccess: async () => { await refresh(); toast.success("Done. The lead is back in the sequence."); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });

  const back = <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit"><Link to="/campaigns"><ArrowLeft aria-hidden /> All campaigns</Link></Button>;
  if (campaign.isLoading) return <div className="grid gap-4" aria-busy="true">{back}<Skeleton className="h-10 w-72" /><Skeleton className="h-40 w-full" /></div>;
  if (campaign.isError || !campaign.data) {
    const missing = campaign.error instanceof ApiError && campaign.error.status === 404;
    return <div className="grid gap-4">{back}<p role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-danger">{missing ? "This campaign was not found. It may have been deleted." : requestFailureMessage(campaign.error)}</p></div>;
  }

  const c = campaign.data;
  const stats = (c as unknown as { stats: { totalLeads: number; invitesSent: number; connected: number; replied: number; interested: number; messagesSent: number; acceptanceRate: number; replyRate: number } }).stats;
  const status = STATUS[c.status] ?? { label: c.status, variant: "muted" as const };
  const m = monitor.data;
  const live = c.status === "active";
  const done = (m?.runCounts.completed ?? 0) + (m?.runCounts.stopped ?? 0);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      {back}
      <PageHeader
        title={c.name}
        description={`${c.leadListName || "No list"} · ${c.stats?.totalLeads ?? 0} leads`}
        actions={
          <>
            <Badge variant={status.variant}>{status.label}</Badge>
            {live && <Button variant="outline" loading={setStatus.isPending} onClick={() => setStatus.mutate("paused")}><Pause aria-hidden /> Pause</Button>}
            {c.status === "paused" && <Button loading={setStatus.isPending} onClick={() => setStatus.mutate("active")}><Play aria-hidden /> Resume</Button>}
            {["draft", "paused", "active"].includes(c.status) && <Button variant="outline" onClick={() => setTab("sequence")}><Pencil aria-hidden /> Edit sequence</Button>}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Leads" value={formatNumber(stats.totalLeads)} hint={`${formatNumber(done)} finished`} />
        <Stat label="Invites sent" value={formatNumber(stats.invitesSent)} />
        <Stat label="Accepted" value={formatNumber(stats.connected)} hint={formatPercent(stats.acceptanceRate, 0)} />
        <Stat label="Messages sent" value={formatNumber(stats.messagesSent)} />
        <Stat label="Replies" value={formatNumber(stats.replied)} hint={formatPercent(stats.replyRate, 0)} />
        <Stat label="Interested" value={formatNumber(stats.interested)} />
      </div>

      <Tabs label="Campaign sections" tabs={TABS} value={tab} onChange={setTab} idPrefix="cp" />

      <TabPanel id="overview" active={tab === "overview"} idPrefix="cp">
        {!m ? <Skeleton className="h-40 w-full" /> : (
          <div className="grid gap-4 lg:grid-cols-2">
            <section aria-labelledby="now-h" className="grid content-start gap-2 rounded-lg border border-border bg-surface p-4">
              <h2 id="now-h" className="text-base font-semibold">What is happening</h2>
              <p className="text-sm">{m.waiting ? m.waiting.message : m.health === "ok" ? "Everything is running normally." : m.health === "attention" ? "Some actions need your attention." : "Nothing is progressing because of failures."}</p>
              <p className="text-sm text-muted-foreground">Now: {m.currentActions.length === 0 ? "nothing in progress" : m.currentActions.map((t) => `${ACTION[t.type] ?? t.type} for ${t.leadName}`).join(", ")}</p>
              <p className="text-sm text-muted-foreground">Last: {m.lastExecuted ? `${ACTION[m.lastExecuted.type] ?? m.lastExecuted.type} for ${m.lastExecuted.leadName} (${m.lastExecuted.status})${m.lastExecuted.updatedAt ? `, ${formatRelative(m.lastExecuted.updatedAt)}` : ""}` : "nothing yet"}</p>
              <p className="text-sm text-muted-foreground">Next: {m.nextScheduled ? `${m.nextScheduled.leadName}, ${new Date(m.nextScheduled.at).getTime() <= Date.now() ? "ready to start" : `in ${formatRelative(m.nextScheduled.at).replace(/^in /, "")}`}` : "nothing scheduled"}</p>
            </section>
            <section aria-labelledby="acc-h" className="grid content-start gap-2 rounded-lg border border-border bg-surface p-4">
              <h2 id="acc-h" className="text-base font-semibold">Sender accounts today</h2>
              {m.accounts.length === 0 && <p className="text-sm text-muted-foreground">No sender account.</p>}
              {m.accounts.map((a) => (
                <p key={a.id} className="flex items-center justify-between gap-2 text-sm"><span>{a.name}{!a.live && <span className="text-danger"> (not connected)</span>}</span><span className="text-muted-foreground">{a.dailyActionsUsed} of {a.dailyActionLimit} actions</span></p>
              ))}
            </section>
            {m.failures.length > 0 && (
              <section aria-labelledby="fail-h" className="grid gap-2 rounded-lg border border-danger/40 bg-danger-soft p-4 lg:col-span-2">
                <h2 id="fail-h" className="text-base font-semibold">Needs attention</h2>
                {m.failures.map((t) => (
                  <div key={t.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span>{ACTION[t.type] ?? t.type} for {t.leadName}: {t.error ?? t.status.replaceAll("_", " ")}</span>
                    <span className="flex gap-2">
                      <Button size="sm" variant="outline" disabled={fix.isPending} onClick={() => fix.mutate({ runId: t.runId, runAction: "retry" })}>Retry</Button>
                      <Button size="sm" variant="outline" disabled={fix.isPending} onClick={() => fix.mutate({ runId: t.runId, runAction: "skip" })}>Skip</Button>
                    </span>
                  </div>
                ))}
              </section>
            )}
          </div>
        )}
      </TabPanel>

      <TabPanel id="leads" active={tab === "leads"} idPrefix="cp">
        {runs.isLoading ? <Skeleton className="h-40 w-full" /> : (runs.data ?? []).length === 0 ? (
          <p role="status" className="rounded-lg border border-border p-4 text-sm text-muted-foreground">No leads have started yet. They appear here once the campaign is running.</p>
        ) : (
          <div className="min-w-0 rounded-lg border border-border bg-surface shadow-raised">
            <Table regionLabel="Lead progress" className="min-w-[44rem]">
              <caption className="sr-only">Each lead's progress in this campaign</caption>
              <TableHeader><TableRow>{["Lead", "Step", "Status", "Next"].map((h) => <th key={h} scope="col" className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>)}</TableRow></TableHeader>
              <TableBody>
                {(runs.data ?? []).map((r) => (
                  <TableRow key={r.runId}>
                    <th scope="row" className="px-4 py-2 text-left font-medium">{r.leadName}<span className="block max-w-[22rem] truncate text-xs font-normal text-muted-foreground">{r.headline}</span></th>
                    <TableCell>{r.stepType ? STEP[r.stepType] ?? r.stepType : "Finished"}</TableCell>
                    <TableCell>{r.stopReason ? STOP[r.stopReason] ?? r.stopReason : RUN[r.status] ?? r.status}</TableCell>
                    <TableCell className="text-muted-foreground">{r.nextActionAt ? formatRelative(r.nextActionAt) : "None"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </TabPanel>

      <TabPanel id="sequence" active={tab === "sequence"} idPrefix="cp">
        {tab === "sequence" && (c.status === "completed" || c.status === "archived"
          ? <p role="note" className="rounded-lg border border-border p-4 text-sm text-muted-foreground">This campaign has finished, so its sequence can no longer be changed.</p>
          : <BuilderPage embedded />)}
      </TabPanel>

      <TabPanel id="settings" active={tab === "settings"} idPrefix="cp">
        <dl className="grid gap-3 rounded-lg border border-border bg-surface p-4 text-sm sm:grid-cols-2">
          {[
            ["Sender accounts", c.accountName || "None"],
            ["Lead list", c.leadListName || "None"],
            ["Time zone", c.schedule.timezone ?? "UTC"],
            ["Daily connection requests", String((c as unknown as { dailyConnectionLimit: number }).dailyConnectionLimit ?? "Default")],
            ["Daily messages", String((c as unknown as { dailyMessageLimit: number }).dailyMessageLimit ?? "Default")],
            ["Stops when someone replies", (c as unknown as { settings: { stopWhenReplied: boolean } }).settings.stopWhenReplied ? "Yes" : "No"],
          ].map(([k, v]) => <div key={k}><dt className="text-xs text-muted-foreground">{k}</dt><dd className="font-medium">{v}</dd></div>)}
        </dl>
      </TabPanel>
    </div>
  );
}
