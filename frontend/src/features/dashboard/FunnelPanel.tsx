import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";
import { useCampaignTable, useFunnel } from "./hooks";
import { exportQuery, type DashboardFilters } from "./service";

const percent = (v: number | null) => (v === null ? "No data" : `${v}%`);

async function download(kind: "campaigns" | "timeseries" | "accounts", filters: DashboardFilters) {
  try {
    const url = URL.createObjectURL(new Blob([await api.getText(`/dashboard/export${exportQuery(filters, kind)}`)], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `synex-${kind}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    toast.error(requestFailureMessage(error));
  }
}

/** The funnel from leads to interested, and each campaign's own numbers. Every figure is counted from real rows; nothing is estimated. */
export function FunnelPanel({ filters }: { filters: DashboardFilters }) {
  const funnel = useFunnel(filters);
  const table = useCampaignTable(filters);
  const stages = funnel.data?.state === "ready" ? funnel.data.data.stages : [];
  const top = Math.max(1, ...stages.map((s) => s.count));
  const rows = table.data?.state === "ready" ? table.data.data : [];

  return (
    <section aria-labelledby="funnel-h" className="grid min-w-0 gap-6 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="funnel-h" className="text-base font-semibold">Funnel</h2>
          <p className="text-sm text-muted-foreground">From leads in campaigns to people who are interested, for the filters above.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void download("timeseries", filters)}><Download aria-hidden /> Export CSV</Button>
      </div>
      {funnel.isLoading && <Skeleton className="h-32 w-full" />}
      {funnel.isError && <p role="alert" className="text-sm text-danger">The funnel could not be loaded. {requestFailureMessage(funnel.error)}</p>}
      {funnel.data?.state === "unavailable" && <p className="text-sm text-muted-foreground">The funnel is not available from this server yet.</p>}
      {stages.length > 0 && stages[0].count === 0 && <p className="text-sm text-muted-foreground">No leads are in a campaign for these filters yet.</p>}
      {stages.length > 0 && (
        <ol aria-label="Funnel stages" className="grid gap-3">
          {stages.map((s) => (
            <li key={s.key} className="grid gap-1">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium">{s.label}</span>
                <span className="tabular-nums">{s.count}{s.percentOfPrevious !== null ? <span className="text-muted-foreground"> ({s.percentOfPrevious}% of the step before)</span> : ""}</span>
              </div>
              <div role="meter" aria-label={`${s.label}: ${s.count}`} aria-valuemin={0} aria-valuemax={top} aria-valuenow={s.count} className="h-2 overflow-hidden rounded-full bg-surface-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${(s.count / top) * 100}%` }} />
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-semibold">By campaign</h3>
          <Button size="sm" variant="outline" disabled={rows.length === 0} onClick={() => void download("campaigns", filters)}><Download aria-hidden /> Export campaigns</Button>
        </div>
        {table.isLoading && <Skeleton className="h-24 w-full" />}
        {table.data?.state === "ready" && rows.length === 0 && <p className="text-sm text-muted-foreground">No campaigns yet.</p>}
        {rows.length > 0 && (
          <div role="region" tabIndex={0} aria-label="Campaign results (scrolls sideways)" className="relative overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[40rem] text-sm">
              <caption className="sr-only">Results for each campaign</caption>
              <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
                <tr>
                  {["Campaign", "Leads", "Contacted", "Accepted", "Replied", "Interested", "Accepted %", "Reply %"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.campaignId} className="border-t border-border">
                    <th scope="row" className="px-3 py-2 text-left font-medium">{r.name}</th>
                    <td className="px-3 py-2 tabular-nums">{r.leads}</td>
                    <td className="px-3 py-2 tabular-nums">{r.contacted}</td>
                    <td className="px-3 py-2 tabular-nums">{r.accepted}</td>
                    <td className="px-3 py-2 tabular-nums">{r.replied}</td>
                    <td className="px-3 py-2 tabular-nums">{r.interested}</td>
                    <td className="px-3 py-2 tabular-nums">{percent(r.acceptedPercent)}</td>
                    <td className="px-3 py-2 tabular-nums">{percent(r.replyPercent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
