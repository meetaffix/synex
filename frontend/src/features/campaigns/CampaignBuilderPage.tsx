import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/PageHeader";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { leadListsService } from "@/services/resources";
import { api } from "@/services/client";

type StepType = "profile_visit" | "connection_request" | "wait" | "message" | "follow_up" | "end";
interface Step {
  key: number;
  type: StepType;
  message: string;
  delayHours: number;
}

const LABELS: Record<StepType, string> = {
  profile_visit: "Visit profile",
  connection_request: "Send connection request (with a note)",
  wait: "Wait",
  message: "Message when connected",
  follow_up: "Follow-up if no reply",
  end: "End",
};
const WRITES: StepType[] = ["connection_request", "message", "follow_up"];
let nextKey = 1;
const newStep = (type: StepType): Step => ({ key: nextKey++, type, message: "", delayHours: type === "wait" ? 48 : 0 });
const starter = (): Step[] => [
  newStep("profile_visit"),
  { ...newStep("wait"), delayHours: 24 },
  newStep("connection_request"),
  { ...newStep("wait"), delayHours: 48 },
  newStep("message"),
  newStep("end"),
];

const zone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
};

/** The builder opens with or without senders and leads; the checklist says what is still missing before launch. */
export function CampaignBuilderPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const accounts = useSenderAccounts();
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list });
  const [name, setName] = useState("Untitled campaign");
  const [accountId, setAccountId] = useState("");
  const [listId, setListId] = useState("");
  const [steps, setSteps] = useState<Step[]>(starter);
  const [invites, setInvites] = useState(5);
  const [messages, setMessages] = useState(5);
  const [startHour, setStartHour] = useState(9);
  const [endHour, setEndHour] = useState(18);

  const account = accounts.data?.find((a) => a.id === accountId);
  const list = lists.data?.find((l) => l.id === listId);
  const checklist = useMemo(() => {
    const actions = steps.filter((s) => s.type !== "wait" && s.type !== "end");
    return [
      { ok: !!account && account.status === "connected", text: account ? "Sender is connected" : "Choose a connected sender account" },
      { ok: !!account && account.dailyActionLimit > 0, text: "Sender's daily limit is above 0" },
      { ok: !!list && list.leadCount > 0, text: list ? `Lead list has leads (${list.leadCount})` : "Choose a lead list with at least one lead" },
      { ok: actions.length > 0, text: "The flow has at least one action" },
      { ok: steps.filter((s) => s.type === "message" || s.type === "follow_up").every((s) => s.message.trim()), text: "Every message is written" },
      { ok: startHour < endHour, text: "Working hours are valid" },
    ];
  }, [account, list, steps, startHour, endHour]);
  const ready = checklist.every((c) => c.ok);

  const save = useMutation({
    mutationFn: async (launch: boolean) => {
      const created = await api.post<{ id: string }>("/campaigns", {
        action: "create",
        name: name.trim() || "Untitled campaign",
        accountId: accountId || null,
        leadListId: listId || null,
        dailyConnectionLimit: invites,
        dailyMessageLimit: messages,
        timezone: zone(),
        startHour,
        endHour,
        workingDays: [0, 1, 2, 3, 4, 5, 6],
        stopWhenReplied: true,
        steps: steps.map((s, order) => ({
          type: s.type,
          order,
          message: WRITES.includes(s.type) ? s.message : null,
          delayHours: s.type === "wait" ? s.delayHours : null,
        })),
      });
      if (launch) await api.post("/campaigns", { action: "update", id: created.id, status: "active" });
      return created;
    },
    onSuccess: async (_c, launch) => {
      await client.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success(launch ? "Campaign launched." : "Draft saved.");
      navigate("/campaigns");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "The campaign could not be saved."),
  });

  const move = (i: number, d: -1 | 1) =>
    setSteps((all) => {
      const j = i + d;
      if (j < 0 || j >= all.length) return all;
      const copy = [...all];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  const patch = (key: number, change: Partial<Step>) => setSteps((all) => all.map((s) => (s.key === key ? { ...s, ...change } : s)));
  const add = (t: StepType) => setSteps((all) => [...all.filter((x) => x.type !== "end"), newStep(t), ...all.filter((x) => x.type === "end")]);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <PageHeader
        title="New campaign"
        description="Build the flow. You can save it as a draft now and add senders or leads later."
        actions={<Button variant="outline" onClick={() => navigate("/campaigns")}>Back to campaigns</Button>}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="grid gap-6">
          <section className="grid gap-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
            <div className="grid gap-2">
              <Label htmlFor="cb-name">Campaign name</Label>
              <Input id="cb-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="cb-sender">Sender account</Label>
                <NativeSelect id="cb-sender" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="">Not chosen yet</option>
                  {(accounts.data ?? []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} {a.dailyActionLimit === 0 ? "(stopped)" : `(up to ${a.dailyActionLimit} a day)`}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cb-list">Lead list</Label>
                <NativeSelect id="cb-list" value={listId} onChange={(e) => setListId(e.target.value)}>
                  <option value="">Not chosen yet</option>
                  {(lists.data ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.leadCount})
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>
          </section>

          <section className="grid gap-3 rounded-lg border border-border bg-surface p-4 sm:p-6">
            <h2 className="text-base font-semibold">Flow</h2>
            <ol className="grid gap-3">
              {steps.map((s, i) => (
                <li key={s.key} className="grid gap-2 rounded-md border border-border bg-surface-muted p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">
                      {i + 1}. {LABELS[s.type]}
                    </span>
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" aria-label="Move up" onClick={() => move(i, -1)} disabled={i === 0}>↑</Button>
                      <Button size="sm" variant="ghost" aria-label="Move down" onClick={() => move(i, 1)} disabled={i === steps.length - 1}>↓</Button>
                      <Button size="sm" variant="ghost" aria-label="Remove step" onClick={() => setSteps((all) => all.filter((x) => x.key !== s.key))}>Remove</Button>
                    </span>
                  </div>
                  {s.type === "wait" && (
                    <div className="flex items-center gap-2 text-sm">
                      <Input type="number" min={1} className="w-24" aria-label="Hours to wait" value={s.delayHours} onChange={(e) => patch(s.key, { delayHours: Math.max(1, Number(e.target.value) || 1) })} />
                      hours
                    </div>
                  )}
                  {WRITES.includes(s.type) && (
                    <Textarea
                      aria-label={`${LABELS[s.type]} text`}
                      placeholder={s.type === "connection_request" ? "Optional note (up to 300 characters). Use {{firstName}}." : "Write the message. Use {{firstName}}."}
                      maxLength={s.type === "connection_request" ? 300 : 2000}
                      value={s.message}
                      onChange={(e) => patch(s.key, { message: e.target.value })}
                    />
                  )}
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap gap-2">
              {(["profile_visit", "connection_request", "wait", "message", "follow_up"] as StepType[]).map((t) => (
                <Button key={t} size="sm" variant="outline" onClick={() => add(t)}>
                  + {LABELS[t].split(" (")[0]}
                </Button>
              ))}
            </div>
          </section>

          <section className="grid gap-4 rounded-lg border border-border bg-surface p-4 sm:grid-cols-4 sm:p-6">
            <div className="grid gap-2">
              <Label htmlFor="cb-inv">Connection requests a day</Label>
              <Input id="cb-inv" type="number" min={0} max={40} value={invites} onChange={(e) => setInvites(Math.max(0, Math.min(40, Number(e.target.value) || 0)))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cb-msg">Messages a day</Label>
              <Input id="cb-msg" type="number" min={0} max={100} value={messages} onChange={(e) => setMessages(Math.max(0, Math.min(100, Number(e.target.value) || 0)))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cb-start">Start hour</Label>
              <Input id="cb-start" type="number" min={0} max={23} value={startHour} onChange={(e) => setStartHour(Number(e.target.value) || 0)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cb-end">End hour</Label>
              <Input id="cb-end" type="number" min={1} max={24} value={endHour} onChange={(e) => setEndHour(Number(e.target.value) || 24)} />
            </div>
          </section>
        </div>

        <aside className="grid h-fit gap-3 rounded-lg border border-border bg-surface p-4 sm:p-6" aria-label="Launch checklist">
          <h2 className="text-base font-semibold">Launch checklist</h2>
          <ul className="grid gap-2 text-sm">
            {checklist.map((c) => (
              <li key={c.text} className={c.ok ? "text-success" : "text-muted-foreground"}>
                {c.ok ? "✓" : "○"} {c.text}
              </li>
            ))}
          </ul>
          <Button variant="outline" disabled={save.isPending} onClick={() => save.mutate(false)}>Save draft</Button>
          <Button disabled={!ready || save.isPending} onClick={() => save.mutate(true)}>Launch</Button>
          {!ready && <p className="text-xs text-muted-foreground">Launch turns on when every item is ticked.</p>}
        </aside>
      </div>
    </div>
  );
}
