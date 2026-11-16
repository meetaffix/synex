import type { Page } from "@playwright/test";
import { API_PORT } from "./support";

/* The API, mocked at the network layer for specs that must not need a backend. Shared by the review, accessibility and
   responsive specs. (Nothing here can reach a real server: every request to the API port is answered below.) */

export interface Call {
  method: string;
  path: string;
  query: string;
  body: Record<string, unknown> | null;
}
export interface AttemptShape {
  attemptId: string;
  state: string;
  challenge?: { type: string; hint?: string };
  error?: { code: string; message: string };
  accountId?: string;
}
export interface Api {
  accounts: Record<string, unknown>[];
  campaigns: Record<string, unknown>[];
  conversations: Record<string, unknown>[];
  messages: Record<string, unknown>[];
  leads: Record<string, unknown>[];
  lists: Record<string, unknown>[];
  feeds: { summary?: unknown; series?: unknown; accounts?: unknown };
  /** Connect attempt states, served one per poll; the last repeats. */
  script: AttemptShape[];
  onCode: (code: string, api: Api) => void;
  proxyTest: (body: Record<string, unknown>) => Record<string, unknown>;
  linkInfo: { status: number; body: Record<string, unknown> };
  listStatus: number;
  linkDelayMs: number;
  /** When set, the matching response waits until the test resolves the promise: the UI's in-between state can be checked without racing a timer. */
  hold: { patch?: Promise<void>; proxyTest?: Promise<void> };
  /** Content publishing data (Others > Content publishing). */
  publishing: { posts: Record<string, unknown>[]; accounts: Record<string, unknown>[]; activity: Record<string, unknown>[] };
  templates: Record<string, unknown>[];
  /** Serve /auth/me as signed out, for the sign-in pages. */
  signedOut: boolean;
  /** Per-account management data (limits policy, lifecycle), created on first read. */
  connections: Record<string, Record<string, { id: string; name: string; headline: string; location: string; profileUrl: string; source: string }[]>>;
  syncStatus: string;
  integ: unknown;
  inbox: Record<string, unknown>[];
  scheduledList: { id: string; body: string; sendAt: string; status: string; error: string | null }[];
  builder: Record<string, unknown> | null;
  launchProblems: { kind: string; field: string; message: string; step: string }[];
  draftCount: number;
  draftsMade: boolean;
  draftsApproved: boolean;
  companyLists: { id: string; name: string; count: number; createdAt: string }[];
  dnc: Record<string, { id: string; kind: string; name: string; profileUrl: string | null; source: string; addedAt: string }[]>;
  management: Record<string, { policy: Record<string, unknown>; lifecycle: string; canChangePrivacy: boolean; voiceId?: string | null }>;
  policyStatus: number;
  calls: Call[];
}

export const post = (id: string, title: string, over: Record<string, unknown> = {}) => ({
  id,
  title,
  body: `${title}. A short post about what the team learned this quarter.`,
  hasImage: false,
  accountId: "p1",
  status: "draft",
  scheduledAt: null,
  timezone: "UTC",
  version: 1,
  attempts: 0,
  error: null,
  linkedinId: null,
  createdAt: "2026-11-10T09:00:00Z",
  updatedAt: "2026-11-12T09:00:00Z",
  ...over,
});

export const publishingAccount = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  name: "Ada Lovelace",
  picture: null,
  email: "ada@example.com",
  status: "connected",
  scopes: ["openid", "profile", "w_member_social"],
  checkedAt: "2026-11-14T10:00:00Z",
  expiresAt: "2027-01-14T10:00:00Z",
  capabilities: { publish: "available", schedule: "available", analytics: "unavailable" },
  ...over,
});

/** A promise the test resolves when it is ready for the held response to go out. */
export function gate() {
  let release = () => {};
  const promise = new Promise<void>((resolve) => (release = resolve));
  return { promise, release };
}

export const USER = { id: "u1", email: "owner@example.com", fullName: "Owner Test", role: "Member", plan: "free", createdAt: "2026-01-01T00:00:00Z" };

export const account = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  headline: "Engineer at Analytical Engines",
  profileUrl: null,
  avatarUrl: null,
  status: "connected",
  dailyActionLimit: 50,
  dailyActionsUsed: 12,
  ceilings: { dailyActions: 200, connectionRequestsPerDay: 40, connectionRequestsPerWeek: 150, messagesPerDay: 100, profileVisitsPerDay: 80, followsPerDay: 50 },
  proxyConfigured: false,
  syncMode: "synex_only",
  canChangeSyncMode: true,
  pausedReason: null,
  lastCheckedAt: "2026-11-14T10:00:00Z",
  connectedAt: "2026-11-01T10:00:00Z",
  ...over,
});

export const CEILINGS: Record<string, [string, number]> = {
  send_invite: ["Connection requests", 40],
  send_message: ["Messages", 100],
  visit_profile: ["Profile views", 80],
  follow_profile: ["Profile follows", 50],
  check_connection: ["Connection checks", 80],
  sync_inbox: ["Inbox reads", 48],
  sync_connections: ["Connection list reads", 12],
  collect_leads: ["Lead collection pages", 20],
};

export const emptyPolicy = () => ({ preset: "off", range: 1, actions: {}, autoWithdraw: false, staleInviteDays: 30, inboxHistoryDays: 90 });

export const campaign = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  status: "active",
  accountId: "a1",
  accountIds: [],
  accountName: "Ada Lovelace",
  leadListName: "Prospects",
  stats: { totalLeads: 40, invitesSent: 30, connected: 12, replied: 5, interested: 2, messagesSent: 14, acceptanceRate: 40, replyRate: 16.7 },
  ...over,
  displayStatus: (over as { displayStatus?: string }).displayStatus ?? ({ active: "running", completed: "finished" } as Record<string, string>)[String((over as { status?: string }).status ?? "active")] ?? String((over as { status?: string }).status),
});

export const conversation = (id: string, leadName: string, over: Record<string, unknown> = {}) => ({
  id,
  leadName,
  leadTitle: "Head of Sales",
  leadCompany: "Acme",
  campaignName: "Q4 outreach",
  lastMessagePreview: "Thanks, tell me more",
  lastMessageAt: "2026-11-14T09:00:00Z",
  unread: true,
  status: "active",
  ...over,
});

export const lead = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  firstName: "Alexandria",
  lastName: "Constantinople-Smith",
  company: "A very long company name incorporated",
  jobTitle: "Head of Partnerships and Enterprise Strategy",
  headline: null,
  linkedinUrl: "https://www.linkedin.com/in/alexandria-constantinople-smith",
  email: "alexandria.constantinople@example.com",
  phone: null,
  location: "San Francisco Bay Area, California",
  industry: null,
  timezone: "America/Los_Angeles",
  connectedAt: null,
  mutualConnections: null,
  tags: [],
  source: "csv",
  status: "new",
  notes: null,
  listIds: [],
  campaignId: null,
  avatarUrl: null,
  createdAt: "2026-11-01T10:00:00Z",
  updatedAt: "2026-11-01T10:00:00Z",
  ...over,
});

export const leadList = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  description: "Organize leads into targeted segments",
  color: "primary",
  leadCount: 12,
  createdAt: "2026-11-01T10:00:00Z",
  ...over,
});

export const attempt = (state: string, extra: Partial<AttemptShape> = {}): AttemptShape => ({ attemptId: "a1", state, ...extra });

export function newApi(over: Partial<Api> = {}): Api {
  return {
    accounts: [],
    campaigns: [],
    conversations: [],
    messages: [],
    leads: [],
    lists: [],
    feeds: {},
    script: [attempt("starting")],
    onCode: () => undefined,
    proxyTest: () => ({ ok: true, latencyMs: 142, exitIp: "203.0.113.7", country: "NL" }),
    linkInfo: { status: 200, body: { accountName: "Ada Lovelace", avatarUrl: null, expiresAt: "2026-11-15T10:00:00Z" } },
    listStatus: 200,
    linkDelayMs: 0,
    hold: {},
    publishing: { posts: [], accounts: [], activity: [] },
    templates: [],
    signedOut: false,
    management: {},
    connections: {},
    syncStatus: "idle",
    integ: { notify: { emails: ["boss@example.com"], account_connected: true, account_disconnected: true, reply_received: false, campaign_paused: true, campaign_launched: false }, outbox: [], keys: [], hooks: [], hubspot: false },
    inbox: [],
    scheduledList: [],
    builder: null,
    launchProblems: [],
    draftCount: 2,
    draftsMade: false,
    draftsApproved: false,
    companyLists: [],
    dnc: { person: [], company: [] },
    policyStatus: 200,
    calls: [],
    ...over,
  };
}

export async function mockApi(page: Page, api: Api) {
  await page.route(
    (url) => url.port === API_PORT,
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method();
      const cors = {
        "access-control-allow-origin": request.headers()["origin"] ?? "*",
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "content-type",
        "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
      };
      if (method === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      let body: Record<string, unknown> | null = null;
      try {
        body = request.postDataJSON();
      } catch {
        body = null;
      }
      const path = url.pathname;
      api.calls.push({ method, path, query: url.search, body });
      const json = (status: number, data: unknown) => route.fulfill({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(data) });
      const empty = () => route.fulfill({ status: 204, headers: cors });

      if (path === "/auth/me") return api.signedOut ? json(401, { detail: "Not signed in" }) : json(200, USER);
      if (path === "/publishing/posts" && method === "GET") return json(200, api.publishing.posts);
      if (path === "/linkedin/accounts" && method === "GET") return json(200, api.publishing.accounts);
      if (path === "/publishing/activity") return json(200, api.publishing.activity);
      if (path === "/publishing/preferences") return json(200, { timezone: "UTC" });
      if (path === "/publishing/metrics")
        return json(200, { counts: { draft: 2, scheduled: 1, published: 4, failed: 0 }, successRate: 100, source: "Synex records" });
      if (path === "/publishing/diagnostics") return json(200, { oauthConfigured: true, workerHealthy: true, workerLastSeen: "2026-11-15T09:00:00Z", aiConfigured: false });
      if (path === "/team") return json(200, { seat: { role: "admin" }, members: [] });
      if (path === "/linkedin/sign-in-identity") return json(200, { linked: false });
      if (path === "/templates" && method === "GET") return json(200, api.templates);
      if (path === "/templates" && method === "POST") return json(200, { id: "t-new", usageCount: 0, replyRate: 0, createdAt: "2026-11-16T10:00:00Z", updatedAt: "2026-11-16T10:00:00Z", ...(body ?? {}) });
      if (path === "/linkedin-accounts" && method === "GET")
        return api.listStatus === 200 ? json(200, api.accounts) : json(api.listStatus, { detail: "The server is unavailable." });
      if (path === "/linkedin-accounts/proxy-test") {
        if (api.hold.proxyTest) await api.hold.proxyTest;
        return json(200, api.proxyTest(body ?? {})).catch(() => undefined);
      }
      if (path === "/campaigns" && (method === "POST" || url.searchParams.has("id"))) {
        const make = () => ({
          id: "cb1", name: "Untitled campaign", status: "draft", accountId: null, accountIds: [], leadListId: null, leadListName: "", dailyConnectionLimit: 20, dailyMessageLimit: 40,
          schedule: { timezone: "UTC" }, weekSchedule: null, exclusions: { other_campaigns: false, reached_other_campaigns: false, reached_same_sender: false, messaged_other_senders: false, existing_connections: false },
          allocation: {}, aiContext: {}, launchSummary: null,
          steps: [
            { id: "s1", type: "connection_request", order: 0, message: "", delayHours: null, aiConfig: null },
            { id: "s2", type: "wait", order: 1, message: null, delayHours: 48, aiConfig: null },
            { id: "s3", type: "message", order: 2, message: "", delayHours: null, aiConfig: null },
            { id: "s4", type: "end", order: 3, message: null, delayHours: null, aiConfig: null }],
        });
        api.builder ??= make();
        const current = api.builder as Record<string, unknown>;
        if (method === "GET") return json(200, current);
        if (body?.action === "import") {
          if (!(body as { sequence?: { synexSequence?: number } }).sequence?.synexSequence) return json(422, { detail: "That is not a Synex sequence file. Use a file made with Share sequence." });
          api.builder = make();
          return json(200, api.builder);
        }
        if (body?.action === "duplicate") return json(200, { ...(api.campaigns.find((c) => c.id === body.id) ?? {}), id: "copy1", name: "Copy of campaign", status: "draft", displayStatus: "draft" });
        if (body?.action === "archive") {
          const target = api.campaigns.find((c) => c.id === body.id);
          if (target) Object.assign(target, { status: "archived", displayStatus: "archived" });
          return json(200, target ?? {});
        }
        if (body?.action === "delete") {
          api.campaigns = api.campaigns.filter((c) => c.id !== body.id);
          return json(200, { ok: true });
        }
        if (body?.action === "create") {
          api.builder = make();
          return json(200, api.builder);
        }
        if (body?.action === "update") {
          const { action: _a, id: _i, steps, ...rest } = body as Record<string, unknown> & { steps?: { id?: string; type: string; message: string | null; delayHours: number | null; aiConfig: unknown }[] };
          if (rest.status === "active" && api.launchProblems.length) return json(422, { detail: api.launchProblems.map((p) => ({ loc: ["body", p.field], msg: p.message, type: `launch.${p.kind}` })) });
          Object.assign(current, rest);
          if (steps) current.steps = steps.map((s, i) => ({ ...s, id: s.id ?? `n${i}`, order: i }));
          return json(200, current);
        }
      }
      const share = path.match(/^\/campaigns\/([^/]+)\/share$/);
      if (share) return json(200, { synexSequence: 1, name: "Autumn outreach", sequenceMode: "classic", aiContext: {}, steps: [{ type: "connection_request", message: "Hi {{first_name}}, from the old campaign", delayHours: null, aiConfig: null }, { type: "end", message: null, delayHours: null, aiConfig: null }] });
      const cbSub = path.match(/^\/campaigns\/cb1\/(launch-check|drafts(?:\/(estimate|generate|approve|preview|render))?)$/);
      if (cbSub) {
        if (cbSub[1] === "launch-check") return json(200, { ready: api.launchProblems.length === 0, problems: api.launchProblems });
        if (cbSub[2] === "estimate") return json(200, { count: api.draftCount, available: api.draftCount, existing: 0, cap: 200, capped: false, provider: "template", estimatedSeconds: api.draftCount * 10, estimatedUsd: 0, note: "No AI service is set up, so drafts come from the built-in templates and cost nothing." });
        if (cbSub[2] === "generate") { api.draftsMade = true; return json(202, { job: { state: "done" } }); }
        if (cbSub[2] === "approve") { api.draftsApproved = true; api.launchProblems = api.launchProblems.filter((p) => !p.kind.startsWith("ai_drafts")); return json(200, { approved: 1 }); }
        if (cbSub[2] === "preview") return json(200, { text: "Hi Ada, loved your work at Engines. Open to a chat?", source: "ai", provider: "template", leadName: "Ada Lovelace", estimatedUsd: 0 });
        if (cbSub[2] === "render") return json(200, { text: String((body as { text?: string })?.text ?? "").replace("{{first_name}}", "Ada").replace("{{missing}}", "{{missing}}"), leadName: "Ada Lovelace", unresolved: String((body as { text?: string })?.text ?? "").includes("{{missing}}") ? ["missing"] : [] });
        if (!cbSub[2]) return json(200, { counts: { proposed: api.draftsMade && !api.draftsApproved ? 1 : 0, approved: api.draftsApproved ? 1 : 0 }, drafts: api.draftsMade ? [{ id: "d1", leadId: "l1", leadName: "Ada Lovelace", stepId: "s3", stepOrder: 2, stepType: "message", body: "Hi Ada, a prepared note.", status: api.draftsApproved ? "approved" : "proposed", source: "template" }] : [], job: null });
      }
      if (path === "/outreach/campaigns/cb1/dry-run") return json(200, { campaignId: "cb1", generatedAt: "2026-11-16T10:00:00Z", actions: [{ leadName: "Ada Lovelace", accountName: "Ada Lovelace", stepType: "connection_request", message: "Hi Ada", earliestAt: "2026-11-17T08:00:00Z", skipReason: null }, { leadName: "Bo B", accountName: null, stepType: null, message: "", earliestAt: null, skipReason: "On the do-not-contact list." }] });
      if (path === "/campaigns") return json(200, api.campaigns);
      if (path === "/assistant/local/status") return json(200, { reachable: api.syncStatus !== "ollama-off", model: "llama3.2", installed: true });
      if (path === "/assistant/local/chat") return json(200, { reply: "Two conversations need a reply.", cards: [{ type: "proposal", proposal: { id: "p1", summary: "Add 1 company to the do-not-contact list.", changes: ["Acme Inc will never be contacted."], status: "pending" } }] });
      if (/^\/assistant\/proposals\/p1\/(confirm|cancel)$/.test(path)) return json(200, { ok: true });
      if (path.startsWith("/integrations/")) {
        const st = api.integ as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
        if (path === "/integrations/events") return json(200, [{ id: "reply_received", label: "A lead replied" }, { id: "campaign_launched", label: "A campaign was launched" }]);
        if (path === "/integrations/notifications" && method === "GET") return json(200, st.notify);
        if (path === "/integrations/notifications" && method === "PUT") { st.notify = body; return json(200, body); }
        if (path === "/integrations/notifications/test") { st.outbox = [{ id: "o1", to: st.notify.emails[0], subject: "Synex: test notification", status: "stored", createdAt: "2026-11-16T10:00:00Z" }]; return json(200, { results: ["stored"], note: "Emails are always saved in the outbox below. They are sent only when SMTP is set up on the server." }); }
        if (path === "/integrations/outbox") return json(200, st.outbox);
        if (path === "/integrations/api-keys" && method === "GET") return json(200, st.keys);
        if (path === "/integrations/api-keys" && method === "POST") { st.keys.push({ id: "k1", name: (body as { name: string }).name, prefix: "syx_abcdefgh", createdAt: "2026-11-16T10:00:00Z", lastUsedAt: null, revoked: false }); return json(201, { id: "k1", key: "syx_abcdefgh_THE_WHOLE_KEY", prefix: "syx_abcdefgh" }); }
        if (path === "/integrations/api-keys/k1" && method === "DELETE") { st.keys[0].revoked = true; return empty(); }
        if (path === "/integrations/webhooks" && method === "GET") return json(200, st.hooks);
        if (path === "/integrations/webhooks" && method === "POST") {
          if (String((body as { url: string }).url).includes("localhost")) return json(422, { detail: "That address points to a private network, which Synex will not call." });
          st.hooks.push({ id: "h1", kind: (body as { kind: string }).kind, url: (body as { url: string }).url, events: (body as { events: string[] }).events, enabled: true });
          return json(201, { ...st.hooks[0], secret: "whsec_SECRET123" });
        }
        if (path === "/integrations/webhooks/h1/test") return json(200, { ok: false, status: 500, error: "The receiver answered 500." });
        if (path === "/integrations/webhooks/h1/deliveries") return json(200, [{ id: "d1", event: "test", status: 500, ok: false, error: "The receiver answered 500.", createdAt: "2026-11-16T10:00:00Z" }]);
        if (path === "/integrations/usage") return json(200, { actionsLast24h: { send_invite: 3 }, aiDraftsThisMonth: 4, assistantMinutesThisMonth: 1.5, leads: 12, campaigns: 2, seatsUsed: 1, month: "2026-11", note: "Synex does not sell credits or plans yet, so this is a meter of what you used, not a balance." });
        if (path === "/integrations/support" && method === "POST") return json(201, { ok: true, note: "Your message is saved in this workspace." });
        if (path === "/integrations/support") return json(200, []);
        if (path === "/integrations/hubspot" && method === "GET") return json(200, { connected: st.hubspot, note: "Built from HubSpot's public API documentation and not verified against a real HubSpot account." });
        if (path === "/integrations/hubspot" && method === "PUT") { st.hubspot = true; return json(200, { connected: true }); }
        if (path === "/integrations/hubspot/import") return json(200, { seen: 3, created: 2, withoutLinkedinAddress: 1 });
        if (path.startsWith("/integrations/exports/")) return route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/csv" }, body: "email,first_name\nada@example.com,Ada\n" });
        if (path === "/integrations/import/leads") return json(200, { created: 2, alreadyKnown: 1, withoutProfileLink: 1, lists: ["Spring"] });
      }
      if (path.startsWith("/inbox/")) {
        const q = url.searchParams;
        const inboxItems = api.inbox as Record<string, unknown>[];
        if (path === "/inbox/conversations") {
          const wantsArchived = q.get("archived") === "true";
          const rows = inboxItems.filter((c) => (wantsArchived ? c.status === "archived" : c.status !== "archived"))
            .filter((c) => q.get("unread") !== "true" || c.unread)
            .filter((c) => q.get("starred") !== "true" || c.starred)
            .filter((c) => q.get("needs_reply") !== "true" || c.needsReply)
            .filter((c) => q.get("i_messaged_last") !== "true" || c.lastDirection === "outbound")
            .filter((c) => !q.get("tag") || (c.tags as string[]).includes(q.get("tag")!))
            .filter((c) => !q.get("interest") || c.interest === q.get("interest"))
            .filter((c) => !q.get("accounts") || q.get("accounts")!.split(",").includes(String(c.accountId)))
            .filter((c) => !q.get("q") || String(c.leadName).toLowerCase().includes(q.get("q")!.toLowerCase()));
          return json(200, { items: rows, total: rows.length });
        }
        if (path === "/inbox/meta")
          return json(200, { accounts: api.accounts.map((a) => ({ id: a.id, name: a.name, lastSyncedAt: "2026-11-16T09:00:00Z", live: true })), campaigns: [{ id: "c1", name: "Autumn outreach" }], tags: ["warm"], interests: [] });
        if (path === "/inbox/bulk") {
          const { ids, action, value } = body as { ids: string[]; action: string; value?: string };
          for (const c of inboxItems.filter((x) => ids.includes(String(x.id)))) {
            if (action === "star") c.starred = true;
            if (action === "unstar") c.starred = false;
            if (action === "read") c.unread = false;
            if (action === "unread") c.unread = true;
            if (action === "archive") c.status = "archived";
            if (action === "unarchive") c.status = "active";
            if (action === "answered") { c.answered = true; c.needsReply = false; }
            if (action === "interest") c.interest = value || null;
            if (action === "tag_add") c.tags = [...(c.tags as string[]), String(value)];
            if (action === "tag_remove") c.tags = (c.tags as string[]).filter((t) => t !== value);
          }
          return json(200, { changed: ids.length });
        }
        if (path === "/inbox/export") return route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/csv" }, body: "name,company\n" + inboxItems.map((c) => `${c.leadName},${c.leadCompany}`).join("\n") });
        if (path === "/inbox/refresh") return json(202, { queued: 1, skipped: [] });
        if (path === "/inbox/suggest-cost") return json(200, { provider: "template", estimatedUsd: 0 });
        const one = path.match(/^\/inbox\/([^/]+)\/(draft|schedule|scheduled|suggest-reply)$/);
        if (one) {
          if (one[2] === "draft") return json(200, { draft: (body as { body: string }).body });
          if (one[2] === "schedule") { api.scheduledList.push({ id: "s1", body: String((body as { body: string }).body), sendAt: String((body as { sendAt: string }).sendAt), status: "pending", error: null }); return json(201, api.scheduledList[0]); }
          if (one[2] === "scheduled") return json(200, api.scheduledList);
          return json(200, { text: "Thanks for getting back to me, Ada. Happy to share more. Does Thursday work?", source: "template", provider: "template" });
        }
        const cancel = path.match(/^\/inbox\/scheduled\/([^/]+)$/);
        if (cancel) { api.scheduledList = []; return empty(); }
      }
      if (path === "/conversations" && method === "POST" && body?.action === "reply") return json(200, { id: "m9", direction: "outbound", body: body.body, sentAt: "2026-11-16T10:00:00Z", deliveryStatus: "queued" });
      if (path === "/conversations") return json(200, url.searchParams.has("conversationId") ? api.messages : api.conversations);
      if (path === "/leads" && method === "GET") return json(200, api.leads);
      const overview = path.match(/^\/leads\/([^/]+)\/(overview|add-to-campaign)$/);
      if (overview) {
        if (overview[2] === "add-to-campaign") return json(200, { added: true, started: false });
        return json(200, { campaigns: [], events: [{ type: "imported", detail: "From a CSV", createdAt: "2026-11-15T10:00:00Z", campaign: null }], doNotContact: api.syncStatus === "blocked" ? "person" : null });
      }
      if (path === "/leads" && method === "POST") return json(200, { id: "new1", tags: [], listIds: [], status: "new", createdAt: "2026-11-16T10:00:00Z", updatedAt: "2026-11-16T10:00:00Z", ...(body ?? {}) });
      if (path === "/lead-lists" && method === "GET") return json(200, api.lists);
      if (path === "/dashboard/summary" && api.feeds.summary) return json(200, api.feeds.summary);
      if (path === "/dashboard/timeseries" && api.feeds.series) return json(200, api.feeds.series);
      if (path === "/dashboard/accounts" && api.feeds.accounts) return json(200, api.feeds.accounts);
      if (path === "/dashboard/funnel" && api.feeds.summary)
        return json(200, { stages: [{ key: "leads", label: "In campaigns", count: 40, percentOfPrevious: null }, { key: "contacted", label: "Contacted", count: 30, percentOfPrevious: 75 }, { key: "accepted", label: "Accepted", count: 12, percentOfPrevious: 40 }, { key: "replied", label: "Replied", count: 5, percentOfPrevious: 41.7 }, { key: "interested", label: "Interested", count: 2, percentOfPrevious: 40 }] });
      if (path === "/dashboard/campaigns" && api.feeds.summary)
        return json(200, [{ campaignId: "c1", name: "Q4 outreach", status: "active", leads: 40, contacted: 30, accepted: 12, replied: 5, interested: 2, acceptedPercent: 40, replyPercent: 41.7 }, { campaignId: "c2", name: "Quiet", status: "paused", leads: 0, contacted: 0, accepted: 0, replied: 0, interested: 0, acceptedPercent: null, replyPercent: null }]);
      if (path === "/dashboard/export") return route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/csv" }, body: "campaign,status\nQ4 outreach,active\n" });
      if (path.startsWith("/dashboard/")) return json(404, { detail: "Not Found" });
      const reconnectInfo = path.match(/^\/reconnect\/([^/]+)$/);
      if (reconnectInfo && method === "GET") return json(api.linkInfo.status, api.linkInfo.body);

      if (path === "/linkedin-accounts/invite-link" && method === "POST")
        return json(200, { url: "http://localhost:5173/reconnect/newtok", expiresAt: "2026-11-30T10:00:00Z" });
      const flow = path.match(/^\/(?:linkedin-accounts|reconnect\/[^/]+)\/connect(?:\/(a1)(\/code)?)?$/);
      if (flow) {
        if (method === "POST" && !flow[1]) return json(202, attempt("starting"));
        if (method === "DELETE") return empty();
        if (method === "POST" && flow[2]) {
          api.onCode(String(body?.code), api);
          return json(200, attempt("starting"));
        }
        const next = api.script.length > 1 ? api.script.shift() : api.script[0];
        if (next?.state === "succeeded" && !api.accounts.some((a) => a.id === "a1")) api.accounts.push(account("a1", "Ada Lovelace"));
        return json(200, next);
      }

      if (path === "/linkedin-accounts/overview")
        return json(200, { plan: "Free", planPlaceholder: true, seatsUsed: api.accounts.length, seatsIncluded: 3, seatsAvailable: Math.max(0, 3 - api.accounts.length),
          accounts: Object.fromEntries(api.accounts.map((a, i) => [a.id, { connections: { used: 2, low: 4, high: 6, budget: 5 }, messages: { used: 1, low: 9, high: 11, budget: 10 }, smart: i === 0,
            performance: i === 0 ? { invited: 20, accepted: 8, replied: 2, acceptedPercent: 40, replyPercent: 25 } : { invited: 0, accepted: 0, replied: 0, acceptedPercent: null, replyPercent: null } }])) });
      if (path === "/lead-collections/sources") return json(200, [{ id: "urls", label: "Paste profile links", readsLinkedin: false, available: true, note: null, maxLeads: 500, produces: "people" }, { id: "csv", label: "CSV or Google Sheets", readsLinkedin: false, available: true, note: null, maxLeads: 500, produces: "people" }, { id: "lists", label: "From my existing lists", readsLinkedin: false, available: true, note: null, maxLeads: 500, produces: "people" }, { id: "search", label: "LinkedIn basic search", readsLinkedin: true, available: true, note: null, maxLeads: 500, produces: "people" }, { id: "post", label: "LinkedIn post reactions or comments", readsLinkedin: true, available: true, note: null, maxLeads: 500, produces: "people" }, { id: "event", label: "LinkedIn event attendees", readsLinkedin: true, available: true, note: "The sender account must be marked as attending the event.", maxLeads: 500, produces: "people" }, { id: "sales_navigator", label: "Sales Navigator leads", readsLinkedin: true, available: true, note: "Needs a Sales Navigator subscription on the sender account.", maxLeads: 500, produces: "people" }, { id: "companies", label: "LinkedIn companies", readsLinkedin: true, available: true, note: null, maxLeads: 500, produces: "companies" }, { id: "group", label: "LinkedIn group members", readsLinkedin: true, available: false, note: "Coming soon: LinkedIn only shows a group's member list to its members.", maxLeads: 500, produces: "people" }]);
      if (path === "/lead-collections/estimate")
        return json(200, { people: Math.min(Number(url.searchParams.get("limit")), 375), pages: 15, minutes: 5, reads_linkedin: true, maxPagesPerRun: 15, pagesLeftToday: url.searchParams.has("accountId") ? 12 : null });
      const coll = path.match(/^\/lead-collections(?:\/(c1)(\/preview|\/run|\/stop)?)?$/);
      if (coll) {
        const base = { id: "c1", label: "Source", listName: "List", limit: 50, options: {}, fetched: 0, created: 0, skipped: {}, detail: null, listId: null, accountId: "a1",
          estimate: { people: 50, pages: 5, minutes: 2, reads_linkedin: true }, createdAt: "2026-11-16T10:00:00Z", source: "event", preview: null };
        const previewData = { people: [{ name: "Katherine Johnson", headline: "Mathematician", company: null, location: "Hampton", degree: 2, profileUrl: "https://www.linkedin.com/in/katherine-j/" }], total: 1, degrees: { "1": 0, "2": 1, "3": 0, unknown: 0 } };
        if (method === "POST" && !coll[1]) {
          if (String((body as { params?: { url?: string } })?.params?.url ?? "").includes("bad")) return json(422, { detail: "Paste a LinkedIn event address (it contains linkedin.com/events/)." });
          api.syncStatus = "draft";
          return json(200, { ...base, status: "draft" });
        }
        if (coll[2] === "/preview") {
          api.syncStatus = "previewing";
          return json(200, { ...base, status: "previewing" });
        }
        if (coll[2] === "/run") {
          api.syncStatus = "completed";
          return json(200, { ...base, status: "completed", created: 1, listName: "Event list", preview: previewData });
        }
        return json(200, { ...base, status: api.syncStatus === "previewing" ? "preview_ready" : api.syncStatus, preview: api.syncStatus === "previewing" ? previewData : null });
      }
      const company = path.match(/^\/company-lists(?:\/([^/]+)(\/do-not-contact)?)?$/);
      if (company) {
        const id = company[1];
        if (!id) return json(200, api.companyLists);
        if (method === "DELETE") {
          api.companyLists = api.companyLists.filter((l) => l.id !== id);
          return empty();
        }
        if (company[2]) return json(200, { added: 2, alreadyListed: 0, invalid: 0 });
        const found = api.companyLists.find((l) => l.id === id);
        return json(200, { id, name: found?.name ?? "", total: 2, items: [
          { id: "e1", name: "Acme Inc", url: "https://www.linkedin.com/company/acme-inc/", industry: "Software Development", location: "London" },
          { id: "e2", name: "Globex", url: "https://www.linkedin.com/company/12345/", industry: "Manufacturing", location: "Boston" }] });
      }
      const dncPath = path.match(/^\/do-not-contact(\/export|\/import|\/([^/]+))?$/);
      if (dncPath) {
        const kind = url.searchParams.get("kind") ?? (body as { kind?: string } | null)?.kind ?? "person";
        const list = (api.dnc[kind] ??= []);
        if (method === "DELETE" && dncPath[2]) {
          for (const k of Object.keys(api.dnc)) api.dnc[k] = api.dnc[k].filter((r) => r.id !== dncPath[2]);
          return empty();
        }
        if (dncPath[1] === "/export") return route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/csv" }, body: "linkedin_url,name,source,added\n" + list.map((r) => `${r.profileUrl ?? r.name},,${r.source},2026-11-16`).join("\n") });
        if (method === "POST") {
          const lines = String((body as { text?: string; csv?: string }).text ?? (body as { csv?: string }).csv ?? "").split("\n").slice(dncPath[1] === "/import" ? 1 : 0).map((l) => l.trim()).filter(Boolean).filter((l) => dncPath[1] !== "/import" || kind === "company" || l.includes("linkedin"));
          const good = lines.filter((l) => (kind === "person" ? l.includes("linkedin.com/in/") : true));
          good.forEach((l, i) => list.push({ id: `d${list.length}${i}`, kind, name: kind === "company" ? l : "", profileUrl: kind === "person" ? l : null, source: dncPath[1] === "/import" ? "csv" : "manual", addedAt: "2026-11-16T10:00:00Z" }));
          return json(200, { added: good.length, alreadyListed: 0, invalid: lines.length - good.length });
        }
        const q = (url.searchParams.get("q") ?? "").toLowerCase();
        const rows = list.filter((r) => !q || `${r.name} ${r.profileUrl ?? ""}`.toLowerCase().includes(q));
        return json(200, { items: rows, total: rows.length });
      }
      const conn = path.match(/^\/linkedin-accounts\/([^/]+)\/connections(\/reload|\/export|\/import)?$/);
      if (conn && api.accounts.some((a) => a.id === conn[1])) {
        const query = url.searchParams;
        const kind = query.get("kind") ?? (body as { kind?: string } | null)?.kind ?? "connection";
        const store = (api.connections[conn[1]] ??= { connection: [], invitation: [] });
        const sync = { status: api.syncStatus, detail: null, lastSyncedAt: null, lastAdded: null };
        const note = "Synex reads your connections a little at a time, so a long list takes a while to fill.";
        if (conn[2] === "/reload") {
          api.syncStatus = "queued";
          return json(202, { sync: { ...sync, status: "queued" }, note });
        }
        if (conn[2] === "/export") {
          const lines = store[kind].map((r) => [r.profileUrl, r.name, r.headline, r.location].join(","));
          return route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/csv" }, body: ["linkedin_url,name,headline,location", ...lines].join("\n") });
        }
        if (conn[2] === "/import") {
          const urls = String((body as { csv: string }).csv).split("\n").slice(1).filter((l) => l.includes("linkedin.com/in/"));
          urls.forEach((u, i) => store.connection.push({ id: `u${i}`, name: u.split("/in/")[1].replace(/[/,].*$/, ""), headline: "", location: "", profileUrl: u.split(",")[0], source: "csv" }));
          return json(200, { added: urls.length, alreadyStored: 0, duplicatesInFile: 0, invalid: 1 });
        }
        const q = (query.get("q") ?? "").toLowerCase();
        const rows = store[kind].filter((r) => !q || `${r.name} ${r.headline} ${r.location}`.toLowerCase().includes(q));
        const offset = Number(query.get("offset") ?? 0);
        return json(200, { items: rows.slice(offset, offset + Number(query.get("limit") ?? 50)), total: rows.length, sync, note });
      }
      if (path === "/linkedin-accounts/voices/catalogue")
        return json(200, { voices: [{ id: "kristin", label: "Kristin", gender: "Female", accent: "English (US)", model: "en_US-kristin-medium", licence: "Public domain" }, { id: "cori", label: "Cori", gender: "Female", accent: "English (UK)", model: "en_GB-cori-medium", licence: "CC BY 4.0" }],
          engine: { name: "Piper", available: false, reason: "The local voice engine (Piper) is not installed, so samples cannot be played yet." },
          clone: { available: false, reason: "Cloning needs an open voice-cloning model with a commercial licence." },
          accents: [{ label: "English (US)", available: true }, { label: "English (India)", available: false, reason: "No Indian English voice with a commercial licence exists in Piper." }] });
      const voice = path.match(/^\/linkedin-accounts\/([^/]+)\/voice$/);
      if (voice && method === "PUT") {
        const st = (api.management[voice[1]] ??= { policy: emptyPolicy(), lifecycle: "active", canChangePrivacy: true });
        st.voiceId = (body as { voiceId: string | null }).voiceId;
        return json(200, { voiceId: st.voiceId });
      }
      const manage = path.match(/^\/linkedin-accounts\/([^/]+)\/(details|policy|deactivate|delete)$/);
      if (manage && api.accounts.some((a) => a.id === manage[1])) {
        const state = (api.management[manage[1]] ??= { policy: emptyPolicy(), lifecycle: "active", canChangePrivacy: true });
        if (manage[2] === "details") {
          const actions = (state.policy.actions ?? {}) as Record<string, { dailyLimit: number; stopAt: number }>;
          const usage = Object.entries(CEILINGS).map(([action, [label, ceiling]]) => {
            const limit = actions[action]?.dailyLimit ?? ceiling;
            return { action, label, used: 3, low: Math.max(0, limit - 1), high: Math.min(ceiling, limit + 1), budget: limit, ceiling };
          });
          return json(200, { accountId: manage[1], voiceId: state.voiceId ?? null, lifecycle: state.lifecycle, activeCampaigns: 1, canChangePrivacy: state.canChangePrivacy, policy: state.policy, usage,
            ssi: null, ssiReason: "No verified LinkedIn SSI data has been collected.", activity: [] });
        }
        if (manage[2] === "policy" && method === "PUT") {
          if (api.policyStatus !== 200) return json(api.policyStatus, { detail: "That limit is above the maximum." });
          state.policy = body ?? state.policy;
          return json(200, state.policy);
        }
        if (manage[2] === "delete" && method === "POST") {
          const acct = api.accounts.find((a) => a.id === manage[1]);
          if (body?.confirm !== acct?.name) return json(422, { detail: "Type the account's name exactly to confirm." });
          api.accounts.splice(api.accounts.indexOf(acct!), 1);
          return empty();
        }
        if (manage[2] === "deactivate" && method === "POST") {
          state.lifecycle = "deactivated";
          return empty();
        }
      }
      const one = path.match(/^\/linkedin-accounts\/([^/]+)(\/check|\/reconnect-link)?$/);
      if (one) {
        const current = api.accounts.find((a) => a.id === one[1]);
        if (one[2] === "/reconnect-link") {
          if (api.linkDelayMs) await new Promise((resolve) => setTimeout(resolve, api.linkDelayMs));
          // A page that was closed or re-routed while the link was "loading" no longer owns this request.
          return json(200, { url: "http://localhost:5173/reconnect/tok123", expiresAt: "2026-11-15T10:00:00Z" }).catch(() => undefined);
        }
        if (method === "PATCH" && current) {
          if (api.hold.patch) await api.hold.patch;
          if (body && "paused" in body) current.status = body.paused ? "paused" : "connected";
          if (body && "dailyActionLimit" in body) current.dailyActionLimit = body.dailyActionLimit;
          if (body && "syncMode" in body) current.syncMode = body.syncMode;
          return json(200, current);
        }
        if (method === "DELETE" && current) {
          current.status = "disconnected";
          return empty();
        }
        if (current) return json(200, current);
      }
      return json(404, { detail: "Not mocked" });
    },
  );
}

export const callsTo = (api: Api, method: string, pattern: RegExp) => api.calls.filter((c) => c.method === method && pattern.test(c.path));

export const inboxItem = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id, leadId: `lead-${id}`, leadName: name, leadTitle: "Head of Sales", leadCompany: "Acme", linkedinUrl: `https://www.linkedin.com/in/${id}/`, accountId: "a1", accountName: "Ada Lovelace",
  campaignId: "c1", campaignName: "Autumn outreach", lastMessagePreview: "Sounds interesting, tell me more", lastMessageAt: "2026-11-16T08:00:00Z", unread: false, status: "active",
  starred: false, answered: false, tags: [] as string[], interest: null as string | null, hasDraft: false, draftBody: "", scheduledCount: 0, lastDirection: "inbound", needsReply: true, ...over,
});
