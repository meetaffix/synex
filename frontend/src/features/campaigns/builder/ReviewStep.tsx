import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { leadListsService } from "@/services/resources";
import { api } from "@/services/client";
import { LABELS } from "./graph";
import { DAYS, DAY_LABEL, EXCLUSIONS, draftsApi, useDrafts, type BuilderState, type Day, type LaunchProblem } from "./model";

const dryRunSchema = (data: unknown) => data as { actions: { leadName: string; accountName: string | null; stepType: string | null; message: string; earliestAt: string | null; skipReason: string | null }[] };
const STEP_NAME: Record<string, string> = { senders: "LinkedIn senders", leads: "List of leads", sequence: "Sequence", review: "this step" };

interface Props {
  state: BuilderState;
  set: (change: Partial<BuilderState>) => void;
  campaignId: string;
  problems: LaunchProblem[] | undefined;
  checking: boolean;
  goTo: (step: number) => void;
  onLaunched: () => void;
  flush: () => Promise<void>;
}

/** Step 4. Everything that stops a launch is listed here with the step that fixes it; the launch button says what is missing. */
export function ReviewStep({ state, set, campaignId, problems, checking, goTo, onLaunched, flush }: Props) {
  const qc = useQueryClient();
  const accounts = useSenderAccounts();
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list });
  const [confirmed, setConfirmed] = useState(false);
  const [dry, setDry] = useState<ReturnType<typeof dryRunSchema> | null>(null);
  const hasAi = state.steps.some((s) => s.aiConfig?.mode === "ai");
  const drafts = useDrafts(campaignId, false);
  const estimate = useQuery({ queryKey: ["draft-estimate", campaignId, state.steps.map((s) => `${s.id}${s.aiConfig?.mode}`).join(), state.leadListId, drafts.data?.drafts.length], enabled: hasAi, queryFn: () => draftsApi.estimate(campaignId) });
  const generate = useMutation({
    mutationFn: async (count: number) => { await flush(); await draftsApi.generate(campaignId, count); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["drafts", campaignId] }),
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const approveAll = useMutation({ mutationFn: () => draftsApi.approve(campaignId, true), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["drafts", campaignId] }); await qc.invalidateQueries({ queryKey: ["launch-check"] }); } });
  const dryRun = useMutation({ mutationFn: async () => { await flush(); return dryRunSchema(await api.post(`/campaigns/${campaignId}/dry-run`)); }, onSuccess: (d) => { setDry(d); setConfirmed(false); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const launch = useMutation({
    mutationFn: async () => { await flush(); await api.post("/campaigns", { action: "update", id: campaignId, status: "active" }); },
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign launched."); onLaunched(); },
    onError: (e) => toast.error(requestFailureMessage(e)),
  });
  const list = lists.data?.find((l) => l.id === state.leadListId);
  const chosen = (accounts.data ?? []).filter((a) => state.accountIds.includes(a.id));
  const blocked = (problems?.length ?? 1) > 0;
  const setDay = (day: Day, change: Partial<BuilderState["week"][Day]>) => set({ week: { ...state.week, [day]: { ...state.week[day], ...change } } });
  const applyToAll = (day: Day) => set({ week: Object.fromEntries(DAYS.map((d) => [d, { ...state.week[d], start: state.week[day].start, end: state.week[day].end }])) as BuilderState["week"] });
  const zones = (() => { try { return Intl.supportedValuesOf("timeZone"); } catch { return ["UTC"]; } })();

  return (
    <section aria-labelledby="review-h" className="grid grid-cols-1 gap-6">
      <div>
        <h2 id="review-h" className="text-lg font-semibold">Review and launch</h2>
        <p className="text-sm text-muted-foreground">Check the schedule, who is left out, and what will be sent. Nothing is sent until you launch.</p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
      <div className="grid min-w-0 gap-6">
      <section aria-labelledby="sched-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
        <h3 id="sched-h" className="text-base font-semibold">Campaign schedule</h3>
        <div className="grid max-w-sm gap-1">
          <Label htmlFor="tz">Time zone</Label>
          <Input id="tz" list="tz-list" autoComplete="off" value={state.timezone} onChange={(e) => set({ timezone: e.target.value })} />
          <datalist id="tz-list">{zones.map((z) => <option key={z} value={z} />)}</datalist>
        </div>
        <p className="text-xs text-muted-foreground">Daily sending is paced by each account&apos;s safety limits, inside the hours you set here.</p>
        <ul aria-label="Operational hours" className="grid gap-2">
          {DAYS.map((d) => (
            <li key={d} className="flex flex-wrap items-center gap-2 text-sm sm:flex-nowrap">
              <label className="flex w-28 shrink-0 items-center gap-2"><Checkbox checked={state.week[d].on} onCheckedChange={(v) => setDay(d, { on: v === true })} aria-label={`${DAY_LABEL[d]} on`} /> {DAY_LABEL[d]}</label>
              <Input aria-label={`${DAY_LABEL[d]} start`} type="time" className="w-[5.75rem] px-2" value={state.week[d].start} disabled={!state.week[d].on} onChange={(e) => setDay(d, { start: e.target.value })} />
              <span aria-hidden>to</span>
              <Input aria-label={`${DAY_LABEL[d]} end`} type="time" className="w-[5.75rem] px-2" value={state.week[d].end} disabled={!state.week[d].on} onChange={(e) => setDay(d, { end: e.target.value })} />
              <Button type="button" size="sm" variant="ghost" className="ml-auto shrink-0 px-2 text-xs" onClick={() => applyToAll(d)}>Apply to all</Button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="list-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
        <h3 id="list-h" className="text-base font-semibold">Lead list</h3>
        <p className="text-sm">{list ? `${list.name}: ${list.leadCount} leads.` : "No lead list selected. Please go back and select a lead list."}</p>
        <ul aria-label="Who is left out" className="grid divide-y divide-border">
          <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span>Do not contact list <Link className="underline underline-offset-2" to="/leads?tab=dnc">Manage list</Link></span>
            <Switch checked disabled onCheckedChange={() => undefined} aria-label="Do not contact list (always on)" />
          </li>
          {EXCLUSIONS.filter((e) => !(e.key === "existing_connections" && (list as { allConnections?: boolean } | undefined)?.allConnections)).map((e) => (
            <li key={e.key} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <span id={`ex-${e.key}`}>{e.label}</span>
              <Switch aria-labelledby={`ex-${e.key}`} checked={!!state.exclusions[e.key]} onCheckedChange={(v) => set({ exclusions: { ...state.exclusions, [e.key]: v } })} />
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">Existing connections are matched by LinkedIn profile against the connection list Synex has read for each sender. <Link className="underline underline-offset-2" to="/linkedin-accounts">Manage connections</Link></p>
      </section>

      </div>
      <div className="grid min-w-0 gap-6">
      <section aria-labelledby="send-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
        <h3 id="send-h" className="text-base font-semibold">Sender accounts</h3>
        <p className="text-sm">{chosen.length ? chosen.map((a) => a.name).join(", ") : "No sender selected."} <Button type="button" variant="link" className="h-auto p-0" onClick={() => goTo(0)}>Edit senders</Button></p>
      </section>

      <section aria-labelledby="seq-sum" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
        <h3 id="seq-sum" className="text-base font-semibold">Campaign sequence</h3>
        <ol className="grid list-decimal gap-1 pl-5 text-sm">
          {state.steps.filter((s) => s.type !== "end").map((s) => (
            <li key={s.key}>{s.type === "wait" ? `Wait ${s.delayHours % 24 === 0 ? `${s.delayHours / 24} day${s.delayHours === 24 ? "" : "s"}` : `${s.delayHours} hours`}` : LABELS[s.type] ?? s.type}{s.aiConfig?.mode === "ai" ? " (written by AI)" : ""}</li>
          ))}
        </ol>
        <p><Button type="button" variant="link" className="h-auto p-0" onClick={() => goTo(2)}>Edit sequence</Button></p>
      </section>

      {hasAi && (
        <section aria-labelledby="ai-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
          <h3 id="ai-h" className="text-base font-semibold">AI messages</h3>
          {estimate.data && (
            <p className="rounded-lg border border-border bg-surface-muted p-3 text-sm" data-testid="ai-estimate">
              {estimate.data.count === 0 ? "Every AI message that can be written already exists." : `${estimate.data.count} AI message${estimate.data.count === 1 ? "" : "s"} to write. About ${Math.max(1, Math.round(estimate.data.estimatedSeconds / 60))} minutes, ${estimate.data.estimatedUsd > 0 ? `about $${estimate.data.estimatedUsd}` : "no cost"}, written by ${estimate.data.provider}.`}
              {estimate.data.capped ? ` Capped at ${estimate.data.cap} for one campaign.` : ""} {estimate.data.note}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!estimate.data || estimate.data.count === 0} loading={generate.isPending || drafts.data?.job?.state === "running"} onClick={() => estimate.data && generate.mutate(estimate.data.count)}>
              {estimate.data ? `Write ${estimate.data.count} AI messages` : "Estimating"}
            </Button>
            <Button variant="outline" disabled={!drafts.data?.counts.proposed} loading={approveAll.isPending} onClick={() => approveAll.mutate()}>Approve all ({drafts.data?.counts.proposed ?? 0})</Button>
          </div>
          {drafts.data?.job?.error && <p role="alert" className="text-sm text-danger">{drafts.data.job.error}</p>}
          <DraftList campaignId={campaignId} />
        </section>
      )}

      <section aria-labelledby="check-h" className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6">
        <h3 id="check-h" className="text-base font-semibold">Launch checklist</h3>
        {checking && <p role="status" className="text-sm text-muted-foreground">Checking.</p>}
        {problems && problems.length === 0 && <p role="status" className="rounded-lg bg-primary-soft px-3 py-2 text-sm text-primary-soft-foreground">Everything needed to launch is in place.</p>}
        {problems && problems.length > 0 && (
          <div role="alert" className="grid gap-2 rounded-lg border border-danger/40 bg-danger-soft p-4">
            <p className="font-medium text-danger">Missing required information</p>
            <ul className="grid gap-2 text-sm">
              {problems.map((p) => (
                <li key={p.kind} className="flex flex-wrap items-center justify-between gap-2">
                  <span>{p.message}</span>
                  {p.step !== "review" && <Button size="sm" variant="outline" onClick={() => goTo(["senders", "leads", "sequence"].indexOf(p.step))}>{`Go to ${STEP_NAME[p.step]}`}</Button>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" loading={dryRun.isPending} onClick={() => dryRun.mutate()}>Preview what would be sent (dry run)</Button>
        </div>
        {dry && (
          <div role="region" tabIndex={0} aria-label="Dry run (scrolls sideways)" className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[34rem] text-sm">
              <caption className="sr-only">The next planned actions. Nothing is sent.</caption>
              <thead className="bg-surface-muted text-left text-xs text-muted-foreground"><tr><th scope="col" className="px-3 py-2">Person</th><th scope="col" className="px-3 py-2">Sender</th><th scope="col" className="px-3 py-2">What</th><th scope="col" className="px-3 py-2">When or why not</th></tr></thead>
              <tbody>
                {dry.actions.length === 0 && <tr><td colSpan={4} className="px-3 py-2 text-muted-foreground">Nothing is planned yet.</td></tr>}
                {dry.actions.slice(0, 20).map((a, i) => (
                  <tr key={i} className="border-t border-border">
                    <th scope="row" className="px-3 py-2 text-left font-medium">{a.leadName}</th>
                    <td className="px-3 py-2">{a.accountName ?? "None"}</td>
                    <td className="px-3 py-2">{a.skipReason ? "Skipped" : `${a.stepType?.replaceAll("_", " ")}${a.message ? `: ${a.message}` : ""}`}</td>
                    <td className="px-3 py-2">{a.skipReason ?? (a.earliestAt ? new Date(a.earliestAt).toLocaleString() : "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={confirmed} disabled={blocked || !dry} onCheckedChange={(v) => setConfirmed(v === true)} /> I have read who is sent to and what is sent, and I confirm the campaign is ready to launch</label>
        {!blocked && !dry && <p className="text-xs text-muted-foreground">Preview what would be sent first. The launch is confirmed against that list.</p>}
        <div>
          <Button size="lg" className="w-full sm:w-auto" disabled={blocked || !confirmed} loading={launch.isPending} onClick={() => launch.mutate()}>
            {blocked ? (problems && problems.length > 0 ? `Fix ${problems.length} thing${problems.length === 1 ? "" : "s"} to launch` : "Checking") : "Launch campaign"}
          </Button>
        </div>
      </section>
      </div>
      </div>
    </section>
  );
}

function DraftList({ campaignId }: { campaignId: string }) {
  const qc = useQueryClient();
  const drafts = useDrafts(campaignId, false);
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null);
  const save = useMutation({ mutationFn: () => draftsApi.edit(campaignId, editing!.id, editing!.body), onSuccess: () => { setEditing(null); return qc.invalidateQueries({ queryKey: ["drafts", campaignId] }); }, onError: (e) => toast.error(requestFailureMessage(e)) });
  const approve = useMutation({ mutationFn: (id: string) => draftsApi.approve(campaignId, false, [id]), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["drafts", campaignId] }); await qc.invalidateQueries({ queryKey: ["launch-check"] }); } });
  if (!drafts.data?.drafts.length) return null;
  return (
    <ul aria-label="AI messages to review" className="grid gap-2">
      {drafts.data.drafts.slice(0, 50).map((d) => (
        <li key={d.id} className="grid gap-2 rounded-lg border border-border p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{d.leadName} <span className="text-muted-foreground">({d.stepType?.replaceAll("_", " ")})</span></span>
            <span className="text-xs text-muted-foreground">{d.status === "approved" ? "Approved" : "Waiting for review"}{d.source === "template" ? ", from the template" : ""}</span>
          </div>
          {editing?.id === d.id ? (
            <>
              <Label htmlFor={`edit-${d.id}`} className="sr-only">Edit message for {d.leadName}</Label>
              <Textarea id={`edit-${d.id}`} rows={3} value={editing.body} onChange={(e) => setEditing({ id: d.id, body: e.target.value })} />
              <div className="flex gap-2"><Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>Save</Button><Button size="sm" variant="outline" onClick={() => setEditing(null)}>Cancel</Button></div>
            </>
          ) : (
            <>
              <p className="whitespace-pre-wrap">{d.body}</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setEditing({ id: d.id, body: d.body })}>Edit</Button>
                {d.status !== "approved" && <Button size="sm" onClick={() => approve.mutate(d.id)}>Approve</Button>}
              </div>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}
