import { expect, type Page } from "@playwright/test";
import { account, attempt, campaign, conversation, lead, leadList, newApi, post, publishingAccount, type Api } from "./mock-api";

/** Every page and dialog state built in Prompts 2, 2B and 3, described once and used by the review screenshots
    and the accessibility checks. */
export interface State {
  name: string;
  path: string;
  api: () => Api;
  /** Moves the page into the state (opens dialogs, advances a connection, and so on). */
  prepare?: (page: Page) => Promise<void>;
  /** Mobile drawer and similar states only exist below the desktop breakpoint. */
  maxWidth?: number;
}

const accounts = () => [
  account("a1", "Ada Lovelace"),
  account("a2", "Grace Hopper with a rather long profile name", { status: "needs_reconnect", pausedReason: "LinkedIn signed this account out. Reconnect it to resume sending.", proxyConfigured: true, dailyActionsUsed: 50 }),
  account("a3", "Margaret Hamilton", { status: "paused", dailyActionsUsed: 0, lastCheckedAt: null }),
  account("a4", "Katherine Johnson", { status: "restricted" }),
  account("a5", "Radia Perlman", { status: "disconnected", headline: null }),
];

const accounts_ = () => newApi({ accounts: accounts() });

const liveFeeds = {
  summary: { connectionsAccepted: 21, leadsContacted: 60, replies: 9, interestedLeads: 4, interestedAnswered: 3, medianResponseSeconds: 7500 },
  series: {
    points: [
      { date: "2026-10-12", requests: 14, accepted: 5, replies: 1 },
      { date: "2026-10-19", requests: 20, accepted: 8, replies: 2 },
      { date: "2026-10-26", requests: 18, accepted: 9, replies: 4 },
      { date: "2026-11-02", requests: 25, accepted: 11, replies: 5 },
    ],
  },
  accounts: [{ accountId: "a1", requestsSent: 45, acceptedPercent: 42, leadsContacted: 44, replyPercent: 15 }],
};

const richFeeds = {
  summary: { connectionsAccepted: 38, leadsContacted: 86, replies: 14, interestedLeads: 6, interestedAnswered: 5, medianResponseSeconds: 5400 },
  series: {
    points: [
      { date: "2026-10-05", requests: 14, accepted: 5, replies: 1 },
      { date: "2026-10-12", requests: 18, accepted: 7, replies: 2 },
      { date: "2026-10-19", requests: 17, accepted: 8, replies: 2 },
      { date: "2026-10-26", requests: 22, accepted: 10, replies: 4 },
      { date: "2026-11-02", requests: 25, accepted: 11, replies: 5 },
      { date: "2026-11-09", requests: 30, accepted: 14, replies: 7 },
    ],
  },
  accounts: [
    { accountId: "a1", requestsSent: 45, acceptedPercent: 42, leadsContacted: 44, replyPercent: 15 },
    { accountId: "a2", requestsSent: 41, acceptedPercent: 36, leadsContacted: 40, replyPercent: 12 },
  ],
};

const richDashboard = (over: Partial<Api> = {}) => () =>
  newApi({
    accounts: [account("a1", "Ada Lovelace", { dailyActionsUsed: 12 }), account("a2", "Grace Hopper", { status: "needs_reconnect", pausedReason: "LinkedIn signed this account out. Reconnect it to resume sending.", dailyActionsUsed: 38 })],
    campaigns: [campaign("c1", "Q4 outreach"), campaign("c2", "Webinar invite", { status: "paused", accountId: "a2" })],
    conversations: [
      conversation("k1", "Jordan Morgan", { lastMessagePreview: "Sounds interesting. Can we talk Thursday?" }),
      conversation("k2", "Priya Raman", { lastMessagePreview: "Thanks, send me the details.", unread: true }),
      conversation("k3", "Sam Lee", { unread: false, lastMessagePreview: "Not now, thanks for asking though" }),
    ],
    leads: [lead("l1"), lead("l2", { firstName: "Sam", lastName: "Lee" })],
    feeds: richFeeds,
    ...over,
  });

const withAccount = (over: Partial<Api> = {}) => () => newApi({ accounts: [account("a1", "Ada Lovelace")], ...over });

async function openConnect(page: Page) {
  await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
  await expect(page.getByRole("dialog").getByLabel("Email or phone")).toBeVisible();
}

async function submitCredentials(page: Page) {
  await page.getByLabel("Email or phone").fill("ada@example.com");
  await page.getByLabel("LinkedIn password").fill("Sup3r-Secret-Pw");
  await page.getByRole("dialog").getByRole("button", { name: "Connect LinkedIn account" }).click();
}

const connectAt = (heading: string | RegExp): State["prepare"] => async (page) => {
  await openConnect(page);
  await submitCredentials(page);
  await expect(page.getByRole("dialog").getByRole("heading", { name: heading })).toBeVisible({ timeout: 15_000 });
};

export const states: State[] = [
  { name: "dashboard-no-account", path: "/dashboard", api: () => newApi() },
  { name: "dashboard-rich", path: "/dashboard", api: richDashboard() },
  {
    name: "dashboard-first-run",
    path: "/dashboard",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace", { dailyActionsUsed: 0, lastCheckedAt: null })] }),
  },
  { name: "welcome", path: "/welcome", api: withAccount() },
  { name: "dashboard-campaign-totals", path: "/dashboard", api: withAccount({ campaigns: [campaign("c1", "Q4 outreach"), campaign("c2", "Webinar invite", { accountId: "a2" })] }) },
  { name: "dashboard-live-feeds", path: "/dashboard", api: withAccount({ campaigns: [campaign("c1", "Q4 outreach")], feeds: liveFeeds }) },
  { name: "inbox-no-account", path: "/inbox", api: () => newApi() },
  { name: "inbox-empty", path: "/inbox", api: withAccount() },
  {
    name: "inbox-thread",
    path: "/inbox",
    api: withAccount({
      conversations: [conversation("k1", "Jane Doe"), conversation("k2", "Sam Lee with a long name here", { unread: false, lastMessagePreview: "Not now, thanks for asking though" })],
      messages: [
        { id: "m1", direction: "outbound", body: "Hi Jane, thanks for connecting.", sentAt: "2026-11-13T09:00:00Z", deliveryStatus: "sent" },
        { id: "m2", direction: "inbound", body: "Thanks, tell me more about what you do.", sentAt: "2026-11-14T09:00:00Z", deliveryStatus: "sent" },
      ],
    }),
    prepare: async (page) => {
      await page.getByRole("list", { name: "Conversations" }).getByRole("button", { name: /Jane Doe/ }).click();
      await expect(page.getByText("Thanks, tell me more about what you do.")).toBeVisible();
    },
  },
  { name: "campaigns-no-account", path: "/campaigns", api: () => newApi() },
  { name: "campaigns-empty", path: "/campaigns", api: withAccount() },
  {
    name: "campaigns-table",
    path: "/campaigns",
    api: () => newApi({ accounts: accounts(), campaigns: [campaign("c1", "Q4 outreach", { accountIds: ["a2", "a3"] }), campaign("c2", "A webinar invitation with a long name", { status: "paused" }), campaign("c3", "Draft", { status: "draft", stats: { totalLeads: 0, invitesSent: 0, connected: 0, replied: 0, interested: 0, messagesSent: 0, acceptanceRate: 0, replyRate: 0 } })] }),
  },
  { name: "sender-empty", path: "/linkedin-accounts", api: () => newApi() },
  { name: "sender-list", path: "/linkedin-accounts", api: () => newApi({ accounts: accounts() }) },
  { name: "sender-list-error", path: "/linkedin-accounts", api: () => newApi({ listStatus: 500 }) },
  { name: "account-limits-new", path: "/linkedin-accounts/a1", api: accounts_ },
  {
    name: "account-limits-custom",
    path: "/linkedin-accounts/a1",
    api: () => newApi({ accounts: accounts(), management: { a1: { policy: { preset: "custom", range: 3, autoWithdraw: false, staleInviteDays: 30, inboxHistoryDays: 90,
      actions: { send_invite: { dailyLimit: 12, increaseBy: 2, stopAt: 30, intervalDays: 3, dynamicInterval: false }, send_message: { dailyLimit: 20, increaseBy: 1, stopAt: 60, intervalDays: 7, dynamicInterval: true } } }, lifecycle: "active", canChangePrivacy: true } } }),
  },
  { name: "account-privacy", path: "/linkedin-accounts/a1?tab=privacy", api: accounts_ },
  { name: "account-privacy-locked", path: "/linkedin-accounts/a1?tab=privacy", api: () => newApi({ accounts: [account("a1", "Ada Lovelace", { canChangeSyncMode: false })], management: { a1: { policy: { preset: "off", range: 1, actions: {}, autoWithdraw: false, staleInviteDays: 30, inboxHistoryDays: 90 }, lifecycle: "active", canChangePrivacy: false } } }) },
  { name: "account-health", path: "/linkedin-accounts/a1?tab=health", api: accounts_ },
  { name: "account-connections", path: "/linkedin-accounts/a1?tab=connections", api: accounts_ },
  { name: "account-lifecycle", path: "/linkedin-accounts/a1?tab=account", api: accounts_ },
  { name: "connect-form", path: "/linkedin-accounts", api: () => newApi(), prepare: openConnect },
  {
    name: "connect-form-options",
    path: "/linkedin-accounts",
    api: () => newApi(),
    prepare: async (page) => {
      await openConnect(page);
      await page.getByText("Sync preferences").click();
      await page.getByText("Advanced: proxy").click();
      await page.getByLabel("Paste a proxy URL").fill("socks5://user:pa%40ss@proxy.example.com:1080");
      await page.getByRole("dialog").getByRole("button", { name: "Test connection" }).click();
      await expect(page.getByText("Proxy works.")).toBeVisible();
    },
  },
  { name: "connect-starting", path: "/linkedin-accounts", api: () => newApi({ script: [attempt("starting")] }), prepare: connectAt("Signing in to LinkedIn") },
  {
    name: "connect-code-rejected",
    path: "/linkedin-accounts",
    api: () => newApi({ script: [attempt("awaiting_code", { challenge: { type: "email_code", hint: "We sent a code to a***@example.com." }, error: { code: "invalid_credentials", message: "That code was not accepted. Enter a new code." } })] }),
    prepare: connectAt("Enter your verification code"),
  },
  { name: "connect-approval", path: "/linkedin-accounts", api: () => newApi({ script: [attempt("awaiting_app_approval")] }), prepare: connectAt("Approve the sign-in in your LinkedIn app") },
  { name: "connect-manual", path: "/linkedin-accounts", api: () => newApi({ script: [attempt("awaiting_manual_verification")] }), prepare: connectAt("LinkedIn needs you to verify this sign-in") },
  {
    name: "connect-failed",
    path: "/linkedin-accounts",
    api: () => newApi({ script: [attempt("failed", { error: { code: "proxy_error", message: "The proxy could not be reached. Check the proxy settings." } })] }),
    prepare: connectAt("Synex could not connect through the proxy"),
  },
  { name: "connect-succeeded", path: "/linkedin-accounts", api: () => newApi({ script: [attempt("succeeded", { accountId: "a1" })] }), prepare: connectAt("Account connected") },
  {
    name: "edit-account",
    path: "/linkedin-accounts",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace", { proxyConfigured: true })] }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "Edit", exact: true }).click();
      await expect(page.getByRole("dialog").getByLabel("Daily action limit")).toBeVisible();
    },
  },
  {
    name: "edit-account-read-only-sync",
    path: "/linkedin-accounts",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace", { canChangeSyncMode: false, syncMode: "all" })] }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "Edit", exact: true }).click();
      await expect(page.getByText("Only the person who connected this account can change this.")).toBeVisible();
    },
  },
  {
    name: "reconnect-link-loading",
    path: "/linkedin-accounts",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace")], linkDelayMs: 4000 }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
      await page.getByRole("menuitem", { name: "Send a link so the owner reconnects it" }).click();
      await expect(page.getByText("Creating the link…")).toBeVisible();
    },
  },
  {
    name: "reconnect-link-ready",
    path: "/linkedin-accounts",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace")] }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
      await page.getByRole("menuitem", { name: "Send a link so the owner reconnects it" }).click();
      await expect(page.getByRole("textbox", { name: "Reconnect link" })).toBeVisible();
    },
  },
  {
    name: "disconnect-confirm",
    path: "/linkedin-accounts",
    api: () => newApi({ accounts: [account("a1", "Ada Lovelace")] }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
      await page.getByRole("menuitem", { name: "Disconnect" }).click();
      await expect(page.getByRole("heading", { name: "Disconnect Ada Lovelace?" })).toBeVisible();
    },
  },
  { name: "public-reconnect-valid", path: "/reconnect/tok123", api: () => newApi() },
  { name: "public-reconnect-expired", path: "/reconnect/old", api: () => newApi({ linkInfo: { status: 404, body: { detail: "expired" } } }) },
  { name: "others", path: "/others", api: withAccount() },
  { name: "help", path: "/help", api: withAccount() },
  { name: "leads-contacts", path: "/leads", api: withAccount({ leads: [lead("l1"), lead("l2", { firstName: "Sam", lastName: "Lee", status: "contacted", company: "Acme", timezone: null })] }) },
  {
    name: "leads-contacts-all-columns",
    path: "/leads",
    api: withAccount({ leads: [lead("l1"), lead("l2", { firstName: "Sam", lastName: "Lee", status: "contacted", company: "Acme", timezone: null, phone: "+44 20 7946 0000", industry: "Software" })] }),
    prepare: async (page) => {
      const columns = page.getByRole("button", { name: "Columns" });
      if (!(await columns.isVisible())) return; // the picker is for tablet widths and up
      await columns.click();
      for (const column of ["Title", "Location", "Phone", "Industry"]) await page.getByRole("menuitemcheckbox", { name: column }).click();
      await page.keyboard.press("Escape");
    },
  },
  { name: "leads-empty", path: "/leads", api: withAccount() },
  { name: "leads-lists", path: "/leads?tab=lists", api: withAccount({ lists: [leadList("g1", "Prospects"), leadList("g2", "A really quite long lead list name for narrow screens", { color: "danger", leadCount: 3 })] }) },
  { name: "leads-lists-empty", path: "/leads?tab=lists", api: withAccount() },
  {
    name: "lead-form",
    path: "/leads",
    api: withAccount({ leads: [lead("l1")] }),
    prepare: async (page) => {
      await page.getByRole("button", { name: "Add lead", exact: true }).first().click();
      await expect(page.getByRole("dialog").getByLabel("Time zone")).toBeVisible();
    },
  },
  {
    name: "shell-user-menu",
    path: "/dashboard",
    api: withAccount(),
    prepare: async (page) => {
      await page.getByRole("button", { name: /account menu/i }).last().click();
      await expect(page.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
    },
  },
  {
    name: "shell-drawer",
    path: "/dashboard",
    api: withAccount(),
    maxWidth: 1023,
    prepare: async (page) => {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
    },
  },
  {
    name: "shell-collapsed",
    path: "/dashboard",
    api: withAccount(),
    prepare: async (page) => {
      const toggle = page.getByRole("button", { name: "Collapse sidebar" });
      if (await toggle.isVisible()) await toggle.click();
    },
  },
  { name: "templates-empty", path: "/templates", api: withAccount() },
  {
    name: "templates-list",
    path: "/templates",
    api: withAccount({
      templates: [
        { id: "t1", name: "Warm connection note", category: "connection", body: "Hi {{first_name}}, I enjoyed your post on hiring.", usageCount: 12, replyRate: 0.25, createdAt: "2026-11-01T09:00:00Z", updatedAt: "2026-11-02T09:00:00Z" },
        { id: "t2", name: "First message after accepting", category: "first_message", body: "Thanks for connecting, {{first_name}}.", usageCount: 4, replyRate: 0, createdAt: "2026-11-01T09:00:00Z", updatedAt: "2026-11-02T09:00:00Z" },
      ],
    }),
  },
  { name: "settings", path: "/settings", api: withAccount() },
  { name: "publishing-overview-new", path: "/others/publishing", api: withAccount() },
  {
    name: "publishing-overview",
    path: "/others/publishing",
    api: withAccount({
      publishing: {
        accounts: [publishingAccount()],
        posts: [post("p-a", "Hiring lessons", { status: "scheduled", scheduledAt: "2026-11-20T09:00:00Z" }), post("p-b", "Quarter in review"), post("p-c", "Launch week", { status: "failed", error: "LinkedIn rejected the image. Try a smaller one." })],
        activity: [{ id: "e1", postId: "p-a", status: "scheduled", detail: "Scheduled for Nov 20, 9:00 AM", createdAt: "2026-11-14T09:00:00Z" }],
      },
    }),
  },
  { name: "publishing-studio", path: "/others/publishing/studio", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [post("p-b", "Quarter in review")], activity: [] } }) },
  { name: "publishing-calendar", path: "/others/publishing/calendar", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [post("p-a", "Hiring lessons", { status: "scheduled", scheduledAt: "2026-11-20T09:00:00Z" })], activity: [] } }) },
  { name: "publishing-queue", path: "/others/publishing/queue", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [post("p-a", "Hiring lessons", { status: "scheduled", scheduledAt: "2026-11-20T09:00:00Z" })], activity: [] } }) },
  { name: "publishing-activity", path: "/others/publishing/activity", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [], activity: [{ id: "e1", postId: "p-a", status: "published", detail: "Published to LinkedIn", createdAt: "2026-11-14T09:00:00Z" }] } }) },
  { name: "publishing-analytics", path: "/others/publishing/analytics", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [], activity: [] } }) },
  { name: "publishing-connections", path: "/others/publishing/connections", api: withAccount({ publishing: { accounts: [publishingAccount()], posts: [], activity: [] } }) },
  { name: "publishing-connections-empty", path: "/others/publishing/connections", api: withAccount() },
  { name: "auth-login", path: "/login", api: () => newApi({ signedOut: true }) },
  { name: "auth-register", path: "/register", api: () => newApi({ signedOut: true }) },
  { name: "auth-forgot", path: "/forgot-password", api: () => newApi({ signedOut: true }) },
  { name: "auth-reset", path: "/reset-password?token=abc", api: () => newApi({ signedOut: true }) },
  { name: "not-found", path: "/no-such-page", api: withAccount() },
  { name: "design", path: "/design", api: withAccount() },
];
