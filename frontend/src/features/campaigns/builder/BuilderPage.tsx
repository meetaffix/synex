import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { ApiError } from "@/services/client";
import { ContextPanel } from "./ContextPanel";
import { LeadsStep } from "./LeadsStep";
import { ReviewStep } from "./ReviewStep";
import { SendersStep } from "./SendersStep";
import { SequenceStep } from "./SequenceStep";
import { problems as nodeProblems } from "./graph";
import { fromServer, useBuilderCampaign, useLaunchCheck, useSaveCampaign, type BuilderState } from "./model";

const STEPS = ["LinkedIn senders", "List of leads", "Sequence", "Review and launch"];
type Saving = "saved" | "dirty" | "saving" | "failed";

/** The four-step campaign builder. It opens with no sender and no leads, saves as you go, and the launch checklist gates the launch. */
export function BuilderPage() {
  const { campaignId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const campaign = useBuilderCampaign(campaignId);
  const save = useSaveCampaign(campaignId);
  const [state, setState] = useState<BuilderState | null>(null);
  const [saving, setSaving] = useState<Saving>("saved");
  const [version, setVersion] = useState(0);
  const [context, setContext] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const latest = useRef<BuilderState | null>(null);
  const dirty = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const check = useLaunchCheck(campaignId, version);
  const step = Math.min(3, Math.max(0, Number(params.get("step") ?? 0) || 0));

  useEffect(() => {
    if (campaign.data && !state) {
      const initial = fromServer(campaign.data);
      setState(initial);
      latest.current = initial;
    }
  }, [campaign.data, state]);

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
      toast.error(`Could not save. ${requestFailureMessage(error)}`);
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
    timer.current = window.setTimeout(() => void persist(), 1500);
  }, [persist]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => { window.removeEventListener("beforeunload", warn); window.clearTimeout(timer.current); };
  }, []);

  const goTo = (next: number) => setParams({ step: String(Math.max(0, Math.min(3, next))) }, { replace: true });
  const back = (
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
  if (!["draft", "paused"].includes(campaign.data.status)) {
    return (
      <div className="grid gap-4">
        {back}
        <p role="note" className="rounded-lg border border-border p-4 text-sm">This campaign has {campaign.data.status === "active" ? "launched and is running" : "finished"}. Pause it from the campaigns list before changing its sequence. <Link className="underline underline-offset-2" to="/campaigns">Back to campaigns</Link></p>
      </div>
    );
  }

  const smartIssues = state.mode === "smart" ? nodeProblems(state.steps) : [];
  const blocked = step === 2 && smartIssues.length > 0 ? smartIssues[0].message : null;
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
          <Button variant="outline" onClick={() => setContext(true)}><Sparkles aria-hidden /> AI campaign context</Button>
        </div>
      </header>

      <nav aria-label="Builder steps">
        <ol className="flex flex-wrap gap-2">
          {STEPS.map((label, i) => (
            <li key={label}>
              <Button type="button" size="sm" variant={i === step ? "default" : "outline"} aria-current={i === step ? "step" : undefined} onClick={() => goTo(i)}>{`${i + 1}. ${label}`}</Button>
            </li>
          ))}
        </ol>
      </nav>

      <div className="min-w-0">
        {step === 0 && <SendersStep state={state} set={change} />}
        {step === 1 && <LeadsStep state={state} set={change} />}
        {step === 2 && <SequenceStep state={state} set={change} campaignId={campaignId} onOpenContext={() => setContext(true)} />}
        {step === 3 && (
          <ReviewStep state={state} set={change} campaignId={campaignId} problems={check.data?.problems} checking={check.isFetching} goTo={goTo}
            flush={persist} onLaunched={() => navigate("/campaigns")} />
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

      {context && <ContextPanel value={state.context} onSave={(value) => change({ context: value })} onClose={() => setContext(false)} />}
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
