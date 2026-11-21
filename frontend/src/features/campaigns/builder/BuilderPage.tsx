import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Check, Lock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { ApiError } from "@/services/client";
import { useAssistantPage } from "@/features/assistant/AssistantProvider";
import { LeadsStep } from "./LeadsStep";
import { ReviewStep } from "./ReviewStep";
import { SendersStep } from "./SendersStep";
import { SequenceStep } from "./SequenceStep";
import { problems as nodeProblems } from "./graph";
import { useQuery } from "@tanstack/react-query";
import { leadListsService } from "@/services/resources";
import { fromServer, useBuilderCampaign, useLaunchCheck, useSaveCampaign, type BuilderState } from "./model";

const STEPS = ["LinkedIn senders", "List of leads", "Sequence", "Review and launch"];
type Saving = "saved" | "dirty" | "saving" | "failed";

/** The four-step campaign builder. It opens with no sender and no leads, saves as you go, and the launch checklist gates the launch. */
/** `embedded` is the sequence map inside the campaign page: no page chrome, and changes are saved on purpose, never by themselves. */
export function BuilderPage({ embedded = false }: { embedded?: boolean } = {}) {
  const { campaignId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const campaign = useBuilderCampaign(campaignId);
  const save = useSaveCampaign(campaignId);
  const [state, setState] = useState<BuilderState | null>(null);
  const [saving, setSaving] = useState<Saving>("saved");
  const [version, setVersion] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const live = useRef(false);
  live.current = embedded || campaign.data?.status === "active";
  const latest = useRef<BuilderState | null>(null);
  const dirty = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const check = useLaunchCheck(campaignId, version);
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list });
  useAssistantPage(campaignId ? { campaignId } : null);
  const requested = Math.min(3, Math.max(0, Number(params.get("step") ?? 0) || 0));

  useEffect(() => {
    if (campaign.data && !state) {
      const initial = fromServer(campaign.data);
      setState(initial);
      latest.current = initial;
    }
  }, [campaign.data, state]);

  // When the assistant writes into this campaign, the server copy changes. Take it unless there are unsaved edits here.
  const seen = useRef(0);
  useEffect(() => {
    if (!campaign.data || !campaign.dataUpdatedAt) return;
    if (seen.current === 0) { seen.current = campaign.dataUpdatedAt; return; }
    if (seen.current === campaign.dataUpdatedAt || dirty.current) return;
    seen.current = campaign.dataUpdatedAt;
    const fresh = fromServer(campaign.data);
    latest.current = fresh;
    setState(fresh);
    setVersion((v) => v + 1);
  }, [campaign.data, campaign.dataUpdatedAt]);

  const persist = useCallback(async () => {
    window.clearTimeout(timer.current);
    if (!dirty.current || !latest.current) return;
    dirty.current = false;
    setSaving("saving");
    try {
      const saved = await save.mutateAsync(latest.current);
      // Keep each step's server id, so drafts and runs stay attached to their step.
      setState((current) => (current && current.steps.length === saved.steps.length ? { ...current, steps: current.steps.map((s, i) => ({ ...s, id: saved.steps[i].id })) } : current));
      if (latest.current && latest.current.steps.length === saved.steps.length) latest.current = { ...latest.current, steps: latest.current.steps.map((s, i) => ({ ...s, id: saved.steps[i].id })) };
      setSaving(dirty.current ? "dirty" : "saved");
      setVersion((v) => v + 1);
    } catch (error) {
      dirty.current = true;
      setSaving("failed");
      toast.error(`Could not save. ${error instanceof ApiError && error.message ? error.message : requestFailureMessage(error)}`);
    }
  }, [save]);

  const change = useCallback((patch: Partial<BuilderState>) => {
    setState((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      latest.current = next;
      return next;
    });
    dirty.current = true;
    setSaving("dirty");
    window.clearTimeout(timer.current);
    // A running campaign is never saved by itself: its changes go live, so they are saved on purpose.
    if (!live.current) timer.current = window.setTimeout(() => void persist(), 1500);
  }, [persist]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => { window.removeEventListener("beforeunload", warn); window.clearTimeout(timer.current); };
  }, []);

  const goTo = (next: number) => setParams({ step: String(Math.max(0, Math.min(3, next))) }, { replace: true });
  const back = embedded ? null : (
    <Button type="button" variant="ghost" size="sm" className="-ml-2 w-fit" onClick={() => (dirty.current ? setLeaving(true) : navigate("/campaigns"))}>
      <ArrowLeft aria-hidden /> All campaigns
    </Button>
  );

  if (campaign.isLoading || (campaign.data && !state)) {
    return <div className="grid gap-4" aria-busy="true">{back}<Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /><p role="status" className="sr-only">Loading the campaign.</p></div>;
  }
  if (campaign.isError || !campaign.data || !state) {
    const missing = campaign.error instanceof ApiError && campaign.error.status === 404;
    return (
      <div className="grid gap-4">
        {back}
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          {missing ? "This campaign was not found. It may have been deleted." : requestFailureMessage(campaign.error)}
          <div className="mt-3"><Button size="sm" variant="outline" onClick={() => void campaign.refetch()}>Try again</Button></div>
        </div>
      </div>
    );
  }
  if (!["draft", "paused", "active"].includes(campaign.data.status)) {
    return (
      <div className="grid gap-4">
        {back}
        <p role="note" className="rounded-lg border border-border p-4 text-sm">This campaign has finished, so its sequence can no longer be changed. <Link className="underline underline-offset-2" to={`/campaigns/${campaignId}`}>Back to the campaign</Link></p>
      </div>
    );
  }

  const audienceConnections = !!lists.data?.find((l) => l.id === state.leadListId)?.allConnections;
  const smartIssues = state.mode === "smart" ? nodeProblems(state.steps, audienceConnections) : [];
  // Like OutFlo: a step opens only when the one before it is done. No sender, no step 2; no leads, no step 3.
  const hasLeads = !!state.leadListId && (lists.data?.find((l) => l.id === state.leadListId)?.leadCount ?? 0) > 0;
  const reachable = state.accountIds.length === 0 ? 0 : !hasLeads ? 1 : state.mode === "smart" && nodeProblems(state.steps, audienceConnections).length > 0 ? 2 : 3;
  const step = Math.min(requested, reachable);
  const blocked = step === 0 && reachable === 0 ? "Choose a sender account."
    : step === 1 && reachable === 1 ? "Choose a lead list with at least one lead, or add leads."
    : step === 2 && smartIssues.length > 0 ? smartIssues[0].message : null;
  if (embedded || campaign.data.status === "active") {
    const unready = nodeProblems(state.steps, audienceConnections);
    const saveChanges = async () => { await persist(); if (!dirty.current) { toast.success("Changes saved. They apply to people who have not reached those steps yet."); if (!embedded) navigate(`/campaigns/${campaignId}`); } };
    const discard = () => { dirty.current = false; if (embedded) { const fresh = fromServer(campaign.data!); latest.current = fresh; setState(fresh); setSaving("saved"); setVersion((v) => v + 1); } else navigate(`/campaigns/${campaignId}`); };
    return (
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
        {!embedded && <Button type="button" variant="ghost" size="sm" className="-ml-2 w-fit" onClick={() => (dirty.current ? setLeaving(true) : navigate(`/campaigns/${campaignId}`))}><ArrowLeft aria-hidden /> Back to the campaign</Button>}
        <header className="grid gap-1">
          {!embedded && <h1 className="text-2xl font-semibold">Edit sequence: {state.name}</h1>}
          <p role="note" className="rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm">{embedded ? "" : "This campaign is running. "}Changes apply to people who have not reached those steps yet, and are saved only when you press Save changes. A step someone is on right now cannot be removed.</p>
        </header>
        <SequenceStep state={state} set={change} campaignId={campaignId} audienceConnections={audienceConnections} running={live.current} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="outline" disabled={embedded && saving !== "dirty" && saving !== "failed"} onClick={() => (dirty.current && !embedded ? setLeaving(true) : discard())}>{embedded ? "Discard changes" : "Cancel"}</Button>
          <div className="flex flex-wrap items-center gap-3">
            {unready.length > 0 && <p id="save-blocked" className="text-sm text-danger">Save is off: {unready[0].message}</p>}
            <Button disabled={saving !== "dirty" && saving !== "failed" || unready.length > 0} aria-describedby={unready.length > 0 ? "save-blocked" : undefined} loading={saving === "saving"} onClick={() => void saveChanges()}>Save changes</Button>
          </div>
        </div>
        <Dialog open={leaving} onOpenChange={setLeaving}>
          <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>Discard unsaved changes?</DialogTitle><DialogDescription>Your changes to the running sequence are not saved. Nothing has changed for the campaign yet.</DialogDescription></DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setLeaving(false)}>Keep editing</Button>
              <Button onClick={discard}>Discard changes</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }
  const indicator = { saved: "Saved", dirty: "Unsaved changes", saving: "Saving", failed: "Not saved: will retry" }[saving];
  return (
    <div className="grid grid-cols-1 gap-6">
      {back}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid min-w-0 flex-1 gap-1 sm:max-w-md">
          <label htmlFor="campaign-name" className="text-sm font-medium">Campaign name</label>
          <Input id="campaign-name" value={state.name} onChange={(e) => change({ name: e.target.value })} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span role="status" aria-live="polite" className="text-sm text-muted-foreground">{indicator}</span>
          <Button variant="outline" disabled={saving === "saved" || saving === "saving"} onClick={() => void persist()}>Save draft</Button>
        </div>
      </header>

      <nav aria-label="Builder steps">
        <ol className="flex flex-wrap items-center gap-x-2 gap-y-3">
          {STEPS.map((label, i) => {
            const done = i < reachable && i !== step;
            const locked = i > reachable;
            return (
              <li key={label} className="flex items-center gap-2">
                <button type="button" disabled={locked} aria-current={i === step ? "step" : undefined} onClick={() => goTo(i)}
                  title={locked ? `Finish step ${reachable + 1} first` : undefined}
                  className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed ${i === step ? "border-primary bg-primary text-primary-foreground" : done ? "border-primary/40 bg-primary-soft text-primary-soft-foreground" : "border-dashed border-border text-muted-foreground"}`}>
                  {(done || locked) && <span aria-hidden className="grid size-5 place-items-center rounded-full bg-background/20 text-xs">{done ? <Check className="size-3" /> : <Lock className="size-3" />}</span>}
                  <span>{`${i + 1}. ${label}`}</span>
                  {locked && <span className="sr-only">(locked until the step before is done)</span>}
                </button>
                {i < STEPS.length - 1 && <span aria-hidden className={`h-px w-4 sm:w-8 ${i < reachable ? "bg-primary" : "bg-border"}`} />}
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="min-w-0">
        {step === 0 && <SendersStep state={state} set={change} />}
        {step === 1 && <LeadsStep state={state} set={change} />}
        {step === 2 && <SequenceStep state={state} set={change} campaignId={campaignId} audienceConnections={audienceConnections} running={live.current} />}
        {step === 3 && (
          <ReviewStep state={state} set={change} campaignId={campaignId} problems={check.data?.problems} checking={check.isFetching} goTo={goTo}
            flush={persist} onLaunched={() => navigate(`/campaigns/${campaignId}`)} />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="outline" disabled={step === 0} onClick={() => goTo(step - 1)}>Back</Button>
        {step < 3 && (
          <div className="flex flex-wrap items-center justify-end gap-3">
            {blocked && <p id="next-blocked" className="text-sm text-danger">Next is off: {blocked}</p>}
            <Button disabled={!!blocked} aria-describedby={blocked ? "next-blocked" : undefined} onClick={() => goTo(step + 1)}>Next</Button>
          </div>
        )}
      </div>

      <Dialog open={leaving} onOpenChange={setLeaving}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Discard unsaved changes?</DialogTitle>
            <DialogDescription>You have changes that are not saved yet. Save them before leaving, or discard them.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => { dirty.current = false; navigate("/campaigns"); }}>Discard changes</Button>
            <Button onClick={async () => { await persist(); setLeaving(false); navigate("/campaigns"); }}>Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
