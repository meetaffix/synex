import { useEffect, useId, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/services/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Radio } from "@/components/ui/radio";
import { Switch } from "@/components/ui/switch";
import { requestFailureMessage } from "../copy";
import {
  PRESET_INFO,
  recommendedActions,
  useManagementActions,
  type AccountDetails,
  type ActionPolicy,
  type Preset,
  type SenderPolicy,
} from "../management";

const PRESETS: { value: Preset; label: string; help: string }[] = [
  { value: "off", label: "Fixed limits", help: "Each limit stays where you set it." },
  { value: "conservative", ...PRESET_INFO.conservative },
  { value: "balanced", ...PRESET_INFO.balanced },
  { value: "aggressive", ...PRESET_INFO.aggressive },
  { value: "custom", label: "Custom", help: "Set how much each action grows, and how often." },
];

const PRESET_SPEED: Record<string, { increaseBy: number; intervalDays: number }> = {
  conservative: { increaseBy: 1, intervalDays: 7 },
  balanced: { increaseBy: 2, intervalDays: 3 },
  aggressive: { increaseBy: 3, intervalDays: 1 },
};

/** The three actions most people care about. Everything else is under "Advanced". */
const MAIN: { action: string; label: string; planKey: "dailyInvites" | "dailyMessages" | "dailyVisits" }[] = [
  { action: "send_invite", label: "Connection requests", planKey: "dailyInvites" },
  { action: "send_message", label: "Messages", planKey: "dailyMessages" },
  { action: "visit_profile", label: "Profile visits", planKey: "dailyVisits" },
];
const PACES: { value: Preset; label: string; help: string }[] = [
  { value: "conservative", label: "Careful", help: "Grows slowly. Safest for a new account." },
  { value: "balanced", label: "Steady", help: "Grows at a normal pace." },
  { value: "aggressive", label: "Fast", help: "Grows quickly. Only for an account with a long history." },
];

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, Number.isFinite(value) ? value : low));

export function SenderLimitsTab({ accountId, details }: { accountId: string; details: AccountDetails }) {
  const id = useId();
  const { savePolicy } = useManagementActions(accountId);
  const [draft, setDraft] = useState<SenderPolicy>(details.policy);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  useEffect(() => setDraft(details.policy), [details.policy]);

  const ceilings = useMemo(() => Object.fromEntries(details.usage.map((row) => [row.action, row.ceiling])), [details.usage]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(details.policy);
  const unconfigured = Object.keys(details.policy.actions).length === 0;
  const suggestions = useMemo(() => recommendedActions(details.usage), [details.usage]);
  const plan = useQuery({ queryKey: ["plan"], queryFn: () => api.get<{ name: string; limits: Record<string, number> }>("/plan"), retry: false, staleTime: 60_000 });
  const testProfile = useQuery({ queryKey: ["safety", "ceilings"], queryFn: () => api.get<{ testProfile: Record<string, number> }>("/outreach/ceilings"), retry: false, staleTime: 60_000 });
  const testActions = useMemo(() => Object.fromEntries(Object.entries(testProfile.data?.testProfile ?? {}).map(([action, n]) =>
    [action, { dailyLimit: n, increaseBy: 0, stopAt: n, intervalDays: 7, dynamicInterval: false }])) as Record<string, ActionPolicy>, [testProfile.data]);

  const setAction = (action: string, change: Partial<ActionPolicy>) =>
    setDraft((current) => {
      const ceiling = ceilings[action] ?? 0;
      const base = current.actions[action] ?? suggestions[action];
      const merged = { ...base, ...change };
      merged.stopAt = clamp(merged.stopAt, 0, ceiling);
      merged.dailyLimit = clamp(merged.dailyLimit, 0, merged.stopAt);
      return { ...current, actions: { ...current.actions, [action]: merged } };
    });

  const save = (next: SenderPolicy) =>
    savePolicy.mutate(next, {
      onSuccess: () => toast.success("Limits saved."),
      onError: (error) => toast.error(requestFailureMessage(error)),
    });

  return (
    <div className="grid grid-cols-1 gap-8">
      {unconfigured && !dismissed && (
        <section aria-labelledby={`${id}-rec`} className="grid gap-3 rounded-lg border border-border bg-surface-muted p-4">
          <h2 id={`${id}-rec`} className="text-base font-semibold">Recommended limits for a new account</h2>
          <p className="text-sm text-muted-foreground">
            This account has no per-action limits yet, so nothing can run. Start low and let them grow: every value stays under Synex's hard maximum for that action.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" loading={savePolicy.isPending} onClick={() => save({ ...draft, preset: "conservative", actions: suggestions })}>
              Apply limits
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDismissed(true)}>Keep current</Button>
            <Button size="sm" variant="ghost" aria-expanded={showSuggestions} onClick={() => setShowSuggestions((value) => !value)}>
              {showSuggestions ? "Hide suggestions" : "Show suggestions"}
            </Button>
          </div>
          {showSuggestions && (
            <ul className="grid gap-1 text-sm">
              {details.usage.map((row) => (
                <li key={row.action}>
                  <span className="font-medium">{row.label}:</span> start at {suggestions[row.action].dailyLimit} a day, growing to {suggestions[row.action].stopAt} (maximum {row.ceiling}).
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {testProfile.data && (
        <section aria-labelledby={`${id}-test`} className="grid gap-2 rounded-lg border border-dashed border-border p-4">
          <h2 id={`${id}-test`} className="text-base font-semibold">Test account profile</h2>
          <p className="text-sm text-muted-foreground">For a test sender: at most 5 profile views, 5 connection requests and 5 messages a day, with random gaps between actions. Everything else is stopped, except the few reads needed to see replies and acceptances.</p>
          <div><Button size="sm" variant="outline" loading={savePolicy.isPending} onClick={() => save({ ...draft, preset: "off", range: 1, actions: testActions })}>Apply the test profile</Button></div>
        </section>
      )}

      <section aria-labelledby={`${id}-usage`} className="grid gap-3">
        <h2 id={`${id}-usage`} className="text-base font-semibold">Last 24 hours</h2>
        <p className="text-sm text-muted-foreground">
          Limits belong to this sender account, not to a campaign. Each day Synex picks a number inside the range, so activity is never the same two days running.
        </p>
        <div tabIndex={0} role="region" aria-label="Usage in the last 24 hours (scrolls sideways)" className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[34rem] text-sm">
            <caption className="sr-only">Actions used in the last 24 hours against today's limits</caption>
            <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Action</th>
                <th scope="col" className="px-3 py-2 font-medium">Sent</th>
                <th scope="col" className="px-3 py-2 font-medium">Today's limit</th>
                <th scope="col" className="px-3 py-2 font-medium">Range</th>
                <th scope="col" className="px-3 py-2 font-medium">Hard maximum</th>
              </tr>
            </thead>
            <tbody>
              {details.usage.map((row) => (
                <tr key={row.action} className="border-t border-border">
                  <th scope="row" className="px-3 py-2 text-left font-medium">{row.label}</th>
                  <td className="px-3 py-2 tabular-nums">{row.sent}{row.queued ? <span className="text-muted-foreground"> (+{row.queued} waiting)</span> : null}</td>
                  <td className="px-3 py-2 tabular-nums">{row.budget === 0 ? "Stopped" : row.budget}</td>
                  <td className="px-3 py-2 tabular-nums">{row.high === 0 ? "0" : `${row.low} to ${row.high}`}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">{row.ceiling}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby={`${id}-simple`} className="grid gap-4 rounded-lg border border-border bg-surface p-4 shadow-raised sm:p-5">
        <div>
          <h2 id={`${id}-simple`} className="text-base font-semibold">Daily sending</h2>
          <p className="text-sm text-muted-foreground">How much this account may send in a day. It starts low and grows at the pace you pick.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {MAIN.map((item) => {
            const row = details.usage.find((u) => u.action === item.action);
            if (!row) return null;
            const current = draft.actions[item.action] ?? suggestions[item.action];
            const planCap = plan.data?.limits?.[item.planKey];
            const top = Math.min(row.ceiling, planCap ?? row.ceiling);
            return (
              <div key={item.action} className="grid content-start gap-1.5 rounded-md bg-surface-muted p-3">
                <label htmlFor={`${id}-s-${item.action}`} className="text-sm font-medium">{item.label}</label>
                <Input id={`${id}-s-${item.action}`} aria-label={`${item.label} per day`} type="number" min={0} max={top} value={current.dailyLimit}
                  onChange={(event) => setAction(item.action, { dailyLimit: clamp(Number(event.target.value), 0, top), stopAt: Math.max(current.stopAt, clamp(Number(event.target.value), 0, top)) })} />
                <p className="text-xs text-muted-foreground">Sent: {row.sent}{row.queued ? `, waiting to be sent: ${row.queued}` : ""}. {planCap !== undefined ? `Your ${plan.data?.name} plan allows up to ${top} a day.` : `Up to ${top} a day.`}</p>
              </div>
            );
          })}
        </div>
        <div role="radiogroup" aria-label="How fast limits grow" className="grid gap-2 sm:grid-cols-3">
          {PACES.map((pace) => (
            <label key={pace.value} className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 ${draft.preset === pace.value ? "border-primary bg-primary-soft" : "border-border"}`}>
              <Radio name={`${id}-pace`} checked={draft.preset === pace.value} onChange={() => setDraft((c) => ({ ...c, preset: pace.value }))} />
              <span className="grid gap-0.5"><span className="text-sm font-medium">{pace.label}</span><span className="text-xs text-muted-foreground">{pace.help}</span></span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" loading={savePolicy.isPending} disabled={!dirty} onClick={() => save(draft)}>Save daily sending</Button>
          {dirty && <span className="text-sm text-muted-foreground">Not saved yet.</span>}
        </div>
      </section>

      <details className="group rounded-lg border border-border bg-surface shadow-raised" open={advancedOpen} onToggle={(event) => setAdvancedOpen((event.currentTarget as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer list-none px-4 py-3 text-base font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
          Advanced: set every action yourself
          <span className="block text-sm font-normal text-muted-foreground">Growth speed, stop values and limits for all {details.usage.length} actions.</span>
        </summary>
      <form
        className="grid grid-cols-1 gap-8 p-4 pt-0"
        onSubmit={(event) => {
          event.preventDefault();
          save(draft);
        }}
      >
        <fieldset className="grid gap-3">
          <legend className="text-base font-semibold">Auto-increase</legend>
          <p className="text-sm text-muted-foreground">How fast each limit grows from where it starts, up to its stop value.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {PRESETS.map((preset) => (
              <div key={preset.value} className="flex items-start gap-3 rounded-lg border border-border p-3">
                <Radio
                  id={`${id}-p-${preset.value}`}
                  name={`${id}-preset`}
                  checked={draft.preset === preset.value}
                  onChange={() => setDraft((current) => ({ ...current, preset: preset.value }))}
                  aria-describedby={`${id}-p-${preset.value}-help`}
                />
                <div className="grid gap-1">
                  <label htmlFor={`${id}-p-${preset.value}`} className="text-sm font-medium">{preset.label}</label>
                  <p id={`${id}-p-${preset.value}-help`} className="text-xs text-muted-foreground">{preset.help}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="grid max-w-xs gap-2">
            <label htmlFor={`${id}-range`} className="text-sm font-medium">Daily variation</label>
            <NativeSelect id={`${id}-range`} value={draft.range} onChange={(event) => setDraft((current) => ({ ...current, range: Number(event.target.value) }))}>
              {Array.from({ length: 10 }, (_, index) => index + 1).map((value) => (
                <option key={value} value={value}>{`Plus or minus ${value}`}</option>
              ))}
            </NativeSelect>
          </div>
        </fieldset>

        <fieldset className="grid gap-3">
          <legend className="text-base font-semibold">Limit for each action</legend>
          <div tabIndex={0} role="region" aria-label="Limits for each action (scrolls sideways)" className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[44rem] text-sm">
              <caption className="sr-only">Daily limit, growth and stop value for every action</caption>
              <thead className="bg-surface-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Action</th>
                  <th scope="col" className="px-3 py-2 font-medium">Daily limit</th>
                  <th scope="col" className="px-3 py-2 font-medium">Increase by</th>
                  <th scope="col" className="px-3 py-2 font-medium">Every (days)</th>
                  <th scope="col" className="px-3 py-2 font-medium">Stop at</th>
                  <th scope="col" className="px-3 py-2 font-medium">Dynamic</th>
                </tr>
              </thead>
              <tbody>
                {details.usage.map((row) => {
                  const current = draft.actions[row.action] ?? { dailyLimit: 0, increaseBy: 0, stopAt: 0, intervalDays: 7, dynamicInterval: false };
                  const preset = PRESET_SPEED[draft.preset];
                  const locked = draft.preset !== "custom";
                  const shownIncrease = draft.preset === "off" ? 0 : preset?.increaseBy ?? current.increaseBy;
                  const shownInterval = preset?.intervalDays ?? current.intervalDays;
                  return (
                    <tr key={row.action} className="border-t border-border">
                      <th scope="row" className="px-3 py-2 text-left font-medium">{row.label}</th>
                      <td className="px-3 py-2">
                        <Input aria-label={`${row.label}: daily limit`} type="number" min={0} max={current.stopAt || row.ceiling} className="w-20" value={current.dailyLimit}
                          onChange={(event) => setAction(row.action, { dailyLimit: Number(event.target.value) })} />
                      </td>
                      <td className="px-3 py-2">
                        <Input aria-label={`${row.label}: increase by`} type="number" min={0} max={10} className="w-20" value={shownIncrease} disabled={locked}
                          onChange={(event) => setAction(row.action, { increaseBy: clamp(Number(event.target.value), 0, 10) })} />
                      </td>
                      <td className="px-3 py-2">
                        <Input aria-label={`${row.label}: every how many days`} type="number" min={1} max={365} className="w-20" value={shownInterval} disabled={locked || current.dynamicInterval}
                          onChange={(event) => setAction(row.action, { intervalDays: clamp(Number(event.target.value), 1, 365) })} />
                      </td>
                      <td className="px-3 py-2">
                        <Input aria-label={`${row.label}: stop at (maximum ${row.ceiling})`} type="number" min={0} max={row.ceiling} className="w-20" value={current.stopAt}
                          onChange={(event) => setAction(row.action, { stopAt: Number(event.target.value) })} />
                        <span className="ml-2 text-xs text-muted-foreground">max {row.ceiling}</span>
                      </td>
                      <td className="px-3 py-2">
                        <Switch aria-label={`${row.label}: dynamic interval (recommended)`} checked={current.dynamicInterval} disabled={locked}
                          onCheckedChange={(checked) => setAction(row.action, { dynamicInterval: checked })} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">
            A limit can never go above the hard maximum shown for its action. A limit of 0 stops that action completely. Changing limits restarts the growth from the new numbers.
          </p>
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={savePolicy.isPending} disabled={!dirty}>Save limits</Button>
          <Button type="button" variant="outline" disabled={!dirty} onClick={() => setDraft(details.policy)}>Discard changes</Button>
          {dirty && <span role="status" className="text-sm text-muted-foreground">You have unsaved changes.</span>}
        </div>
      </form>
      </details>
    </div>
  );
}
