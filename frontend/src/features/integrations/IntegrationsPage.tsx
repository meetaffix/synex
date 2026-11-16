import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { api } from "@/services/client";
import { leadListsService } from "@/services/resources";
import { formatRelative } from "@/utils/format";

const TABS = [
  { id: "notifications", label: "Notifications" },
  { id: "webhooks", label: "Webhooks and Slack" },
  { id: "api", label: "API and MCP" },
  { id: "email", label: "Email tools" },
  { id: "hubspot", label: "HubSpot" },
  { id: "import", label: "Import" },
  { id: "usage", label: "Usage" },
  { id: "support", label: "Support" },
];

const useJson = <T,>(key: string[], path: string) => useQuery({ queryKey: key, queryFn: () => api.get<T>(path), retry: false });
const fail = (e: unknown) => toast.error(e instanceof Error && e.message ? e.message : requestFailureMessage(e));

export function IntegrationsPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") ?? "notifications";
  const tab = TABS.some((t) => t.id === requested) ? requested : "notifications";
  return (
    <div className="grid grid-cols-1 gap-6">
      <PageHeader title="Integrations" description="Notifications, webhooks, API keys, exports and imports. Nothing here needs a paid service." actions={<Button asChild variant="outline"><Link to="/settings">Back to settings</Link></Button>} />
      <Tabs label="Integration sections" tabs={TABS} value={tab} idPrefix="int" onChange={(next) => setParams({ tab: next }, { replace: true })} />
      <TabPanel id="notifications" active={tab === "notifications"} idPrefix="int"><NotificationsTab /></TabPanel>
      <TabPanel id="webhooks" active={tab === "webhooks"} idPrefix="int"><WebhooksTab /></TabPanel>
      <TabPanel id="api" active={tab === "api"} idPrefix="int"><ApiTab /></TabPanel>
      <TabPanel id="email" active={tab === "email"} idPrefix="int"><EmailToolsTab /></TabPanel>
      <TabPanel id="hubspot" active={tab === "hubspot"} idPrefix="int"><HubspotTab /></TabPanel>
      <TabPanel id="import" active={tab === "import"} idPrefix="int"><ImportTab /></TabPanel>
      <TabPanel id="usage" active={tab === "usage"} idPrefix="int"><UsageTab /></TabPanel>
      <TabPanel id="support" active={tab === "support"} idPrefix="int"><SupportTab /></TabPanel>
    </div>
  );
}

/* ----------------------------------------------------------------------------------------------- notifications */

interface Notify { emails: string[]; account_connected: boolean; account_disconnected: boolean; reply_received: boolean; campaign_paused: boolean; campaign_launched: boolean }
const NOTIFY_LABELS: [keyof Omit<Notify, "emails">, string][] = [["account_connected", "A sender account is connected"], ["account_disconnected", "A sender account is disconnected"], ["reply_received", "Any message from a lead"], ["campaign_paused", "A campaign is paused"], ["campaign_launched", "A campaign is launched"]];

function NotificationsTab() {
  const qc = useQueryClient();
  const settings = useJson<Notify>(["int", "notify"], "/integrations/notifications");
  const outbox = useJson<{ id: string; to: string; subject: string; status: string; createdAt: string }[]>(["int", "outbox"], "/integrations/outbox");
  const [draft, setDraft] = useState<Notify | null>(null);
  const [text, setText] = useState<string | null>(null);
  const value = draft ?? settings.data;
  const save = useMutation({
    mutationFn: (v: Notify) => api.put<Notify>("/integrations/notifications", v),
    onSuccess: (v) => { qc.setQueryData(["int", "notify"], v); setDraft(null); setText(null); toast.success("Notification settings saved."); },
    onError: fail,
  });
  const test = useMutation({ mutationFn: () => api.post<{ results: string[]; note: string }>("/integrations/notifications/test"), onSuccess: (r) => { toast.success(r.note); void qc.invalidateQueries({ queryKey: ["int", "outbox"] }); }, onError: fail });
  if (!value) return <p role="status" className="text-sm text-muted-foreground">{settings.isError ? "Notification settings could not be loaded." : "Loading."}</p>;
  const emails = text ?? value.emails.join(", ");
  const parsed = emails.split(/[,\s]+/).filter(Boolean);
  return (
    <section aria-labelledby="notif-h" className="grid max-w-2xl gap-5">
      <div><h2 id="notif-h" className="text-base font-semibold">Notification emails</h2><p className="text-sm text-muted-foreground">Who hears about what happens in this workspace. Emails are always saved below, and sent only when the server has SMTP set up.</p></div>
      <div className="grid gap-2"><Label htmlFor="notify-emails">Email addresses (separate with commas)</Label><Input id="notify-emails" value={emails} onChange={(e) => { setText(e.target.value); setDraft({ ...value, emails: e.target.value.split(/[,\s]+/).filter(Boolean) }); }} /></div>
      <ul aria-label="What to notify about" className="grid gap-3">
        {NOTIFY_LABELS.map(([key, label]) => (
          <li key={key} className="flex items-center justify-between gap-3 text-sm"><span id={`n-${key}`}>{label}</span><Switch aria-labelledby={`n-${key}`} checked={value[key]} onCheckedChange={(v) => setDraft({ ...value, [key]: v })} /></li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!draft} loading={save.isPending} onClick={() => draft && save.mutate({ ...draft, emails: parsed })}>Save changes</Button>
        <Button variant="outline" loading={test.isPending} disabled={!settings.data?.emails.length || !!draft} onClick={() => test.mutate()}>Send a test email</Button>
      </div>
      <div><h3 className="text-sm font-semibold">Outbox</h3>
        {outbox.data?.length ? <ul aria-label="Recent emails" className="mt-1 grid gap-1 text-sm">{outbox.data.map((m) => <li key={m.id}>{m.subject} to {m.to} <span className="text-muted-foreground">({m.status}, {formatRelative(m.createdAt)})</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No emails yet.</p>}</div>
    </section>
  );
}

/* ----------------------------------------------------------------------------------------------- webhooks, Slack */

interface Hook { id: string; kind: string; url: string; events: string[]; enabled: boolean; secret?: string }
function WebhooksTab() {
  const qc = useQueryClient();
  const hooks = useJson<Hook[]>(["int", "hooks"], "/integrations/webhooks");
  const events = useJson<{ id: string; label: string }[]>(["int", "events"], "/integrations/events");
  const [kind, setKind] = useState<"webhook" | "slack">("webhook");
  const [url, setUrl] = useState("");
  const [chosen, setChosen] = useState<string[]>(["reply_received"]);
  const [secret, setSecret] = useState<string | null>(null);
  const [log, setLog] = useState<{ id: string; rows: { id: string; event: string; status: number | null; ok: boolean; error: string | null }[] } | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["int", "hooks"] });
  const create = useMutation({
    mutationFn: () => api.post<Hook>("/integrations/webhooks", { kind, url, events: chosen }),
    onSuccess: (h) => { setUrl(""); setSecret(h.secret ?? null); toast.success(kind === "slack" ? "Slack connected." : "Webhook added."); void refresh(); },
    onError: fail,
  });
  const toggle = useMutation({ mutationFn: (v: { id: string; enabled: boolean }) => api.patch(`/integrations/webhooks/${v.id}`, { enabled: v.enabled }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => api.delete(`/integrations/webhooks/${id}`), onSuccess: () => { toast.success("Removed."); void refresh(); } });
  const test = useMutation({
    mutationFn: (id: string) => api.post<{ ok: boolean; status: number | null; error: string | null }>(`/integrations/webhooks/${id}/test`),
    onSuccess: (r) => (r.ok ? toast.success("The receiver accepted the test.") : toast.error(r.error ?? "The receiver did not accept the test.")),
  });
  const showLog = async (id: string) => setLog({ id, rows: await api.get(`/integrations/webhooks/${id}/deliveries`) });
  return (
    <section aria-labelledby="hook-h" className="grid max-w-3xl gap-5">
      <div><h2 id="hook-h" className="text-base font-semibold">Webhooks and Slack</h2><p className="text-sm text-muted-foreground">Synex calls your address when something happens, with a signature in the X-Synex-Signature header so you can check it came from here. Slack uses an incoming webhook address.</p></div>
      <div className="grid gap-3 rounded-lg border border-border p-4">
        <div className="grid gap-1"><Label htmlFor="hook-kind">Type</Label><NativeSelect id="hook-kind" value={kind} onChange={(e) => setKind(e.target.value as "webhook" | "slack")}><option value="webhook">Webhook</option><option value="slack">Slack</option></NativeSelect></div>
        <div className="grid gap-1"><Label htmlFor="hook-url">{kind === "slack" ? "Slack webhook address" : "Webhook address"}</Label><Input id="hook-url" value={url} placeholder="https://" onChange={(e) => setUrl(e.target.value)} /></div>
        <fieldset className="grid gap-2"><legend className="mb-1 text-sm font-medium">Send these events</legend>
          {(events.data ?? []).map((ev) => <label key={ev.id} className="flex items-center gap-2 text-sm"><Checkbox checked={chosen.includes(ev.id)} onCheckedChange={(v) => setChosen(v === true ? [...chosen, ev.id] : chosen.filter((x) => x !== ev.id))} /> {ev.label}</label>)}
        </fieldset>
        <div><Button disabled={!url.trim() || chosen.length === 0} loading={create.isPending} onClick={() => create.mutate()}>{kind === "slack" ? "Connect Slack" : "Add webhook"}</Button></div>
        {secret && <p role="status" className="rounded-lg bg-primary-soft p-3 text-sm text-primary-soft-foreground">Signing secret (used to check the signature): <code className="break-all">{secret}</code></p>}
      </div>
      {hooks.data?.length === 0 && <p className="text-sm text-muted-foreground">No webhooks yet.</p>}
      <ul aria-label="Webhooks" className="grid gap-3">
        {(hooks.data ?? []).map((h) => (
          <li key={h.id} className="grid gap-2 rounded-lg border border-border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{h.kind === "slack" ? "Slack" : "Webhook"}</span><span className="break-all text-muted-foreground">{h.url}</span><span className="ml-auto flex items-center gap-2"><span id={`en-${h.id}`}>Enabled</span><Switch aria-labelledby={`en-${h.id}`} checked={h.enabled} onCheckedChange={(v) => toggle.mutate({ id: h.id, enabled: v })} /></span></div>
            <p className="text-xs text-muted-foreground">Events: {h.events.join(", ")}</p>
            <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => test.mutate(h.id)}>Send test</Button><Button size="sm" variant="outline" onClick={() => void showLog(h.id)}>Delivery log</Button><Button size="sm" variant="ghost" className="text-danger" onClick={() => remove.mutate(h.id)}>Remove</Button></div>
            {log?.id === h.id && <ul aria-label="Deliveries" className="grid gap-1 text-xs">{log.rows.length === 0 ? <li className="text-muted-foreground">Nothing sent yet.</li> : log.rows.map((r) => <li key={r.id}>{r.event}: {r.ok ? "delivered" : `failed${r.status ? ` (${r.status})` : ""}${r.error ? `. ${r.error}` : ""}`}</li>)}</ul>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ----------------------------------------------------------------------------------------------- API and MCP */

interface Key { id: string; name: string; prefix: string; lastUsedAt: string | null; revoked: boolean; scopes?: string[] }
function ApiTab() {
  const qc = useQueryClient();
  const keys = useJson<Key[]>(["int", "keys"], "/integrations/api-keys");
  const [name, setName] = useState("");
  const [canWrite, setCanWrite] = useState(false);
  const [fresh, setFresh] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["int", "keys"] });
  const create = useMutation({ mutationFn: () => api.post<{ key: string }>("/integrations/api-keys", { name: name || "API key", scopes: canWrite ? ["read", "write"] : ["read"] }), onSuccess: (r) => { setFresh(r.key); setName(""); void refresh(); }, onError: fail });
  const revoke = useMutation({ mutationFn: (id: string) => api.delete(`/integrations/api-keys/${id}`), onSuccess: () => { toast.success("Key revoked."); void refresh(); } });
  const base = typeof window !== "undefined" ? window.location.origin.replace(/:\d+$/, ":8010") : "";
  return (
    <section aria-labelledby="api-h" className="grid max-w-3xl gap-5">
      <div><h2 id="api-h" className="text-base font-semibold">API keys</h2><p className="text-sm text-muted-foreground">A key lets another program read your campaigns, leads and conversations and, if you allow it, add leads. Keys are limited to 60 requests a minute. The same key connects an AI client over MCP.</p></div>
      <div className="flex flex-wrap items-end gap-3"><div className="grid gap-1"><Label htmlFor="key-name">Key name</Label><Input id="key-name" value={name} placeholder="My CRM" onChange={(e) => setName(e.target.value)} /></div><label className="flex items-center gap-2 text-sm"><Checkbox checked={canWrite} onCheckedChange={(v) => setCanWrite(v === true)} /> Allow adding leads (otherwise read only)</label><Button loading={create.isPending} onClick={() => create.mutate()}>Create key</Button></div>
      {fresh && <p role="status" className="rounded-lg bg-primary-soft p-3 text-sm text-primary-soft-foreground">Copy this key now. It is shown only once: <code className="break-all">{fresh}</code></p>}
      <ul aria-label="API keys" className="grid gap-2 text-sm">
        {(keys.data ?? []).map((k) => <li key={k.id} className="flex flex-wrap items-center gap-2"><span className="font-medium">{k.name}</span><code>{k.prefix}…</code><span className="text-muted-foreground">{k.scopes?.includes("write") ? "Read and add leads" : "Read only"}</span><span className="text-muted-foreground">{k.revoked ? "Revoked" : k.lastUsedAt ? `Used ${formatRelative(k.lastUsedAt)}` : "Never used"}</span>{!k.revoked && <Button size="sm" variant="ghost" className="ml-auto text-danger" onClick={() => revoke.mutate(k.id)}>Revoke</Button>}</li>)}
        {keys.data?.length === 0 && <li className="text-muted-foreground">No keys yet.</li>}
      </ul>
      <div className="grid gap-2 text-sm">
        <h3 className="font-semibold">Using the API</h3>
        <p>Send the key as <code>Authorization: Bearer syx_…</code>. Endpoints: <code>GET {base}/public/v1/campaigns</code>, <code>/public/v1/leads</code>, <code>/public/v1/conversations</code>, and <code>POST /public/v1/leads</code>.</p>
        <h3 className="font-semibold">Connect an AI client (MCP)</h3>
        <p>MCP address: <code>{base}/mcp</code> with the same bearer key. It offers Synex&apos;s read and draft tools. Tools that change data are not offered, because they need your confirmation click inside Synex.</p>
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------------------------------------- email tools, import */

function EmailToolsTab() {
  const lists = useQuery({ queryKey: ["lead-lists"], queryFn: leadListsService.list });
  const [listId, setListId] = useState("");
  const get = async (tool: "smartlead" | "instantly") => {
    try {
      const url = URL.createObjectURL(new Blob([await api.getText(`/integrations/exports/${tool}?listId=${listId}`)], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `synex-${tool}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { fail(e); }
  };
  return (
    <section aria-labelledby="mail-h" className="grid max-w-2xl gap-4">
      <div><h2 id="mail-h" className="text-base font-semibold">Export to an email tool</h2><p className="text-sm text-muted-foreground">Download a list as a CSV that Smartlead or Instantly can import. Only people with an email address are included; Synex never guesses one. Copy your message text into the tool.</p></div>
      <div className="grid gap-1"><Label htmlFor="mail-list">Lead list</Label><NativeSelect id="mail-list" value={listId} onChange={(e) => setListId(e.target.value)}><option value="">Choose a list</option>{(lists.data ?? []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</NativeSelect></div>
      <div className="flex flex-wrap gap-2"><Button disabled={!listId} onClick={() => void get("smartlead")}>Download for Smartlead</Button><Button disabled={!listId} variant="outline" onClick={() => void get("instantly")}>Download for Instantly</Button></div>
    </section>
  );
}

function ImportTab() {
  const [text, setText] = useState("");
  const [listColumn, setListColumn] = useState("");
  const run = useMutation({
    mutationFn: () => api.post<{ created: number; alreadyKnown: number; withoutProfileLink: number; lists: string[] }>("/integrations/import/leads", { csv: text, listColumn: listColumn || undefined }),
    onSuccess: (r) => toast.success(`${r.created} added, ${r.alreadyKnown} already known, ${r.withoutProfileLink} without a profile link. Lists: ${r.lists.join(", ")}.`),
    onError: fail,
  });
  return (
    <section aria-labelledby="imp-h" className="grid max-w-2xl gap-4">
      <div><h2 id="imp-h" className="text-base font-semibold">Import from another tool</h2><p className="text-sm text-muted-foreground">Bring leads from a HeyReach, OutFlo or similar CSV export. Columns are matched by name. Campaigns and conversation history are not imported.</p></div>
      <div className="grid gap-1"><Label htmlFor="imp-file">CSV file</Label><input id="imp-file" type="file" accept=".csv,text/csv" onChange={async (e) => { const f = e.target.files?.[0]; if (f && f.size < 5_000_000) setText(await f.text()); }} /></div>
      <div className="grid gap-1"><Label htmlFor="imp-col">Column that holds the list or campaign name (optional)</Label><Input id="imp-col" value={listColumn} placeholder="Campaign" onChange={(e) => setListColumn(e.target.value)} /></div>
      <div><Button disabled={!text} loading={run.isPending} onClick={() => run.mutate()}>Import leads</Button></div>
    </section>
  );
}

/* ----------------------------------------------------------------------------------------------- HubSpot, usage, support */

function HubspotTab() {
  const qc = useQueryClient();
  const status = useJson<{ connected: boolean; note: string }>(["int", "hubspot"], "/integrations/hubspot");
  const [token, setToken] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["int", "hubspot"] });
  const connect = useMutation({ mutationFn: () => api.put("/integrations/hubspot", { token }), onSuccess: () => { setToken(""); toast.success("HubSpot connected."); void refresh(); }, onError: fail });
  const disconnect = useMutation({ mutationFn: () => api.delete("/integrations/hubspot"), onSuccess: () => { toast.success("HubSpot disconnected."); void refresh(); } });
  const run = useMutation({ mutationFn: () => api.post<{ seen: number; created: number; withoutLinkedinAddress: number }>("/integrations/hubspot/import"), onSuccess: (r) => toast.success(`${r.created} contacts added, ${r.withoutLinkedinAddress} skipped for having no LinkedIn address.`), onError: fail });
  return (
    <section aria-labelledby="hs-h" className="grid max-w-2xl gap-4">
      <div><h2 id="hs-h" className="text-base font-semibold">HubSpot</h2><p className="text-sm text-muted-foreground">Import HubSpot contacts that have a LinkedIn address into a list called HubSpot contacts. Use a private app token with permission to read contacts.</p></div>
      <p role="note" className="rounded-lg border border-border bg-surface-muted p-3 text-xs text-muted-foreground">{status.data?.note ?? "Not verified against a real HubSpot account."}</p>
      {status.data?.connected ? (
        <div className="flex flex-wrap gap-2"><Button loading={run.isPending} onClick={() => run.mutate()}>Import contacts</Button><Button variant="outline" onClick={() => disconnect.mutate()}>Disconnect</Button></div>
      ) : (
        <div className="grid gap-2"><Label htmlFor="hs-token">Private app token</Label><Input id="hs-token" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} /><div><Button disabled={token.length < 10} loading={connect.isPending} onClick={() => connect.mutate()}>Connect HubSpot</Button></div></div>
      )}
    </section>
  );
}

function UsageTab() {
  const usage = useJson<{ actionsLast24h: Record<string, number>; aiDraftsThisMonth: number; assistantMinutesThisMonth: number; leads: number; campaigns: number; seatsUsed: number; note: string }>(["int", "usage"], "/integrations/usage");
  if (!usage.data) return <p role="status" className="text-sm text-muted-foreground">{usage.isError ? "Usage could not be loaded." : "Loading."}</p>;
  const u = usage.data;
  return (
    <section aria-labelledby="use-h" className="grid max-w-2xl gap-4">
      <div><h2 id="use-h" className="text-base font-semibold">Usage</h2><p className="text-sm text-muted-foreground">{u.note}</p></div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="text-muted-foreground">Sender seats in use</dt><dd className="font-medium">{u.seatsUsed}</dd></div>
        <div><dt className="text-muted-foreground">Leads</dt><dd className="font-medium">{u.leads}</dd></div>
        <div><dt className="text-muted-foreground">Campaigns</dt><dd className="font-medium">{u.campaigns}</dd></div>
        <div><dt className="text-muted-foreground">AI messages written this month</dt><dd className="font-medium">{u.aiDraftsThisMonth}</dd></div>
        <div><dt className="text-muted-foreground">Assistant minutes this month</dt><dd className="font-medium">{u.assistantMinutesThisMonth}</dd></div>
      </dl>
      <div><h3 className="text-sm font-semibold">LinkedIn actions in the last 24 hours</h3>
        {Object.keys(u.actionsLast24h).length === 0 ? <p className="text-sm text-muted-foreground">None.</p> : <ul className="text-sm">{Object.entries(u.actionsLast24h).map(([k, v]) => <li key={k}>{k.replaceAll("_", " ")}: {v}</li>)}</ul>}</div>
    </section>
  );
}

function SupportTab() {
  const qc = useQueryClient();
  const mine = useJson<{ id: string; subject: string; createdAt: string }[]>(["int", "support"], "/integrations/support");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const send = useMutation({ mutationFn: () => api.post<{ note: string }>("/integrations/support", { subject, body }), onSuccess: (r) => { setSubject(""); setBody(""); toast.success(r.note); void qc.invalidateQueries({ queryKey: ["int", "support"] }); }, onError: fail });
  return (
    <section aria-labelledby="sup-h" className="grid max-w-2xl gap-4">
      <div><h2 id="sup-h" className="text-base font-semibold">Support</h2><p className="text-sm text-muted-foreground">Write down a problem or a question. It is saved in this workspace for whoever runs this installation. There is no support team behind it yet.</p></div>
      <div className="grid gap-1"><Label htmlFor="sup-subject">Subject</Label><Input id="sup-subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
      <div className="grid gap-1"><Label htmlFor="sup-body">Message</Label><Textarea id="sup-body" rows={4} value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div><Button disabled={subject.trim().length < 3 || body.trim().length < 10} loading={send.isPending} onClick={() => send.mutate()}>Send message</Button></div>
      {mine.data?.length ? <ul aria-label="Your messages" className="text-sm">{mine.data.map((m) => <li key={m.id}>{m.subject} <span className="text-muted-foreground">({formatRelative(m.createdAt)})</span></li>)}</ul> : null}
    </section>
  );
}
