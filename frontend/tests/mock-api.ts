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
  management: Record<string, { policy: Record<string, unknown>; lifecycle: string; canChangePrivacy: boolean }>;
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
      if (path === "/linkedin-accounts" && method === "GET")
        return api.listStatus === 200 ? json(200, api.accounts) : json(api.listStatus, { detail: "The server is unavailable." });
      if (path === "/linkedin-accounts/proxy-test") {
        if (api.hold.proxyTest) await api.hold.proxyTest;
        return json(200, api.proxyTest(body ?? {})).catch(() => undefined);
      }
      if (path === "/campaigns") return json(200, api.campaigns);
      if (path === "/conversations") return json(200, url.searchParams.has("conversationId") ? api.messages : api.conversations);
      if (path === "/leads" && method === "GET") return json(200, api.leads);
      if (path === "/lead-lists" && method === "GET") return json(200, api.lists);
      if (path === "/dashboard/summary" && api.feeds.summary) return json(200, api.feeds.summary);
      if (path === "/dashboard/timeseries" && api.feeds.series) return json(200, api.feeds.series);
      if (path === "/dashboard/accounts" && api.feeds.accounts) return json(200, api.feeds.accounts);
      if (path.startsWith("/dashboard/")) return json(404, { detail: "Not Found" });
      const reconnectInfo = path.match(/^\/reconnect\/([^/]+)$/);
      if (reconnectInfo && method === "GET") return json(api.linkInfo.status, api.linkInfo.body);

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
        return json(200, { plan: "Free", planPlaceholder: true, seatsUsed: api.accounts.length, seatsIncluded: 3, seatsAvailable: Math.max(0, 3 - api.accounts.length) });
      const manage = path.match(/^\/linkedin-accounts\/([^/]+)\/(details|policy|deactivate)$/);
      if (manage && api.accounts.some((a) => a.id === manage[1])) {
        const state = (api.management[manage[1]] ??= { policy: emptyPolicy(), lifecycle: "active", canChangePrivacy: true });
        if (manage[2] === "details") {
          const actions = (state.policy.actions ?? {}) as Record<string, { dailyLimit: number; stopAt: number }>;
          const usage = Object.entries(CEILINGS).map(([action, [label, ceiling]]) => {
            const limit = actions[action]?.dailyLimit ?? ceiling;
            return { action, label, used: 3, low: Math.max(0, limit - 1), high: Math.min(ceiling, limit + 1), budget: limit, ceiling };
          });
          return json(200, { accountId: manage[1], lifecycle: state.lifecycle, activeCampaigns: 1, canChangePrivacy: state.canChangePrivacy, policy: state.policy, usage,
            ssi: null, ssiReason: "No verified LinkedIn SSI data has been collected.", activity: [] });
        }
        if (manage[2] === "policy" && method === "PUT") {
          if (api.policyStatus !== 200) return json(api.policyStatus, { detail: "That limit is above the maximum." });
          state.policy = body ?? state.policy;
          return json(200, state.policy);
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
