import { Link } from "react-router-dom";
import { Check } from "lucide-react";
import { Illustration } from "@/components/brand/Illustration";
import { ProgressRing } from "@/components/charts/ProgressRing";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Reveal } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useOnboarding } from "./useOnboarding";

/** The first-run checklist on the dashboard. It stays until every step is done, and can be dismissed once they are. */
export function OnboardingChecklist() {
  const { steps, doneCount, complete, loading, dismissed, dismiss, firstOpen } = useOnboarding();
  if (dismissed) return null;
  if (loading) return <Skeleton role="status" aria-label="Loading your setup steps" className="h-48 w-full rounded-lg" />;

  if (complete) {
    return (
      <section aria-labelledby="onboarding-title" className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-surface p-4 shadow-raised">
        <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-success-soft text-success"><Check className="size-5" /></span>
        <div className="min-w-[14rem] flex-1">
          <h2 id="onboarding-title" className="text-base font-semibold">You are set up</h2>
          <p className="text-sm text-muted-foreground">Every step is done. Your campaigns run inside working hours and daily limits.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={dismiss}>Hide this checklist</Button>
      </section>
    );
  }

  return (
    <section aria-labelledby="onboarding-title" className="grid gap-6 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto]">
      <div className="grid gap-4">
        <div className="flex items-center gap-4">
          <ProgressRing done={doneCount} total={steps.length} />
          <div className="grid gap-1">
            <h2 id="onboarding-title" className="text-xl font-semibold">
              {complete ? "You are set up" : "Get Synex working for you"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {complete ? "Every step is done. Your campaigns run inside working hours and daily limits." : `${steps.length - doneCount} ${steps.length - doneCount === 1 ? "step" : "steps"} left. Each one opens where you do it.`}
            </p>
          </div>
        </div>
        <ol className="grid gap-2">
          {steps.map((step, index) => (
            <Reveal as="li" key={step.id} index={index} className={cn("flex flex-wrap items-start gap-3 rounded-md p-3", step.id === firstOpen?.id ? "bg-primary-soft" : "")}>
              <span
                aria-hidden
                className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold", step.done ? "border-primary bg-primary text-primary-foreground" : "border-input text-muted-foreground")}
              >
                {step.done ? <Check className="size-4" /> : index + 1}
              </span>
              <div className="min-w-[12rem] flex-1">
                <p className={cn("text-sm font-medium", step.id === firstOpen?.id && "text-primary-soft-foreground")}>
                  {step.title}
                  <span className="sr-only">{step.done ? " (done)" : " (not done)"}</span>
                </p>
                <p className={cn("text-xs", step.id === firstOpen?.id ? "text-primary-soft-foreground" : "text-muted-foreground")}>{step.detail}</p>
                {!step.done && step.note && <p className={cn("mt-1 text-xs", step.id === firstOpen?.id ? "text-primary-soft-foreground" : "text-muted-foreground")}>{step.note}</p>}
              </div>
              {!step.done && step.action && (
                <Button asChild size="sm" variant={step.id === firstOpen?.id && !step.note ? "default" : "secondary"} className="shrink-0 max-sm:ml-9">
                  <Link to={step.action.to}>{step.action.label}</Link>
                </Button>
              )}
            </Reveal>
          ))}
        </ol>
        {complete && (
          <div>
            <Button variant="secondary" onClick={dismiss}>
              Hide this checklist
            </Button>
          </div>
        )}
      </div>
      <Illustration name="onboarding" className="hidden h-36 self-center lg:block" />
    </section>
  );
}
