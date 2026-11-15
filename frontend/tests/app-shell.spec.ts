import { test, expect, type Page } from "@playwright/test";
import { API_PORT } from "./support";

/* The API is mocked at the network layer; no backend or LinkedIn is involved. */

interface Call {
  method: string;
  path: string;
  query: string;
}
interface Api {
  accounts: Record<string, unknown>[];
  campaigns: Record<string, unknown>[];
  conversations: Record<string, unknown>[];
  messages: Record<string, unknown>[];
  /** Dashboard feeds that exist on the mocked server. */
  feeds: { summary?: unknown; series?: unknown; accounts?: unknown };
  calls: Call[];
}

const USER = { id: "u1", email: "owner@example.com", fullName: "Owner Test", role: "Member", plan: "free", createdAt: "2026-01-01T00:00:00Z" };
const account = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id,
  name,
  headline: "Engineer",
  profileUrl: null,
  avatarUrl: null,
  status: "connected",
  dailyActionLimit: 50,
  dailyActionsUsed: 0,
  ceilings: { dailyActions: 200, connectionRequestsPerDay: 40, connectionRequestsPerWeek: 150, messagesPerDay: 100, profileVisitsPerDay: 80, followsPerDay: 50 },
  proxyConfigured: false,
  syncMode: "synex_only",
  canChangeSyncMode: true,
  pausedReason: null,
  lastCheckedAt: null,
  connectedAt: null,
  ...over,
});
const campaign = (id: string, name: string, over: Record<string, unknown> = {}) => ({
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
const conversation = (id: string, leadName: string, over: Record<string, unknown> = {}) => ({
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

function newApi(over: Partial<Api> = {}): Api {
  return { accounts: [], campaigns: [], conversations: [], messages: [], feeds: {}, calls: [], ...over };
}

async function mockApi(page: Page, api: Api) {
  await page.route(
    (url) => url.port === API_PORT,
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const cors = {
        "access-control-allow-origin": request.headers()["origin"] ?? "*",
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "content-type",
        "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
      };
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      api.calls.push({ method: request.method(), path: url.pathname, query: url.search });
      const json = (status: number, data: unknown) => route.fulfill({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(data) });
      const path = url.pathname;
      if (path === "/auth/me") return json(200, USER);
      if (path === "/linkedin-accounts") return json(200, api.accounts);
      if (path === "/campaigns") return json(200, api.campaigns);
      if (path === "/conversations") return json(200, url.searchParams.has("conversationId") ? api.messages : api.conversations);
      if (path === "/dashboard/summary" && api.feeds.summary) return json(200, api.feeds.summary);
      if (path === "/dashboard/timeseries" && api.feeds.series) return json(200, api.feeds.series);
      if (path === "/dashboard/accounts" && api.feeds.accounts) return json(200, api.feeds.accounts);
      if (path.startsWith("/dashboard/")) return json(404, { detail: "Not Found" });
      if (path === "/leads" || path === "/lead-lists") return json(200, []);
      return json(404, { detail: "Not mocked" });
    },
  );
}

const sidebar = (page: Page) => page.getByRole("complementary", { name: "Sidebar" });
const primary = (page: Page) => sidebar(page).getByRole("navigation", { name: "Primary" });
const calls = (api: Api, pathname: string) => api.calls.filter((c) => c.path === pathname);

test.describe("app shell", () => {
  test.setTimeout(60_000);

  test("primary sidebar order, footer, and active states", async ({ page }) => {
    const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
    await mockApi(page, api);
    await page.goto("/dashboard");

    await expect(primary(page).getByRole("link")).toHaveText(["Dashboard", "Inbox", "Campaigns", "Sender accounts", "Leads", "Templates", "Others"]);
    await expect(sidebar(page).getByRole("navigation", { name: "Secondary" }).getByRole("link")).toHaveText(["Settings", "Help"]);
    await expect(sidebar(page).getByRole("button", { name: /Owner Test.*account menu/i })).toBeVisible();
    await expect(primary(page).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");

    await primary(page).getByRole("link", { name: "Inbox" }).click();
    await expect(page).toHaveURL(/\/inbox$/);
    await expect(primary(page).getByRole("link", { name: "Inbox" })).toHaveAttribute("aria-current", "page");
    await expect(primary(page).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current", "page");

    await sidebar(page).getByRole("link", { name: "Help" }).click();
    await expect(page).toHaveURL(/\/help$/);
    await expect(sidebar(page).getByRole("link", { name: "Help" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "Help", level: 1 })).toBeVisible();
  });

  test("nothing about posting is in the sidebar", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/dashboard");
    const text = (await sidebar(page).innerText()).toLowerCase();
    for (const word of ["studio", "calendar", "publishing", "content", "analytics", "post"]) expect(text).not.toContain(word);
  });

  test("publishing is reachable only through Others, and old addresses redirect", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/dashboard");
    await primary(page).getByRole("link", { name: "Others" }).click();
    await expect(page.getByRole("heading", { name: "Others", level: 1 })).toBeVisible();

    await page.getByRole("link", { name: /Content publishing/ }).click();
    await expect(page).toHaveURL(/\/others\/publishing$/);
    const section = page.getByRole("navigation", { name: "Content publishing" });
    await expect(section.getByRole("link")).toHaveText(["Overview", "Studio", "Calendar", "Queue", "Activity", "Analytics", "Connections"]);

    await section.getByRole("link", { name: "Studio" }).click();
    await expect(page).toHaveURL(/\/others\/publishing\/studio$/);
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toHaveText(/Others\s*\/\s*Content publishing\s*\/\s*Studio/);
    await expect(crumbs.getByRole("link", { name: "Others" })).toBeVisible();
    await expect(crumbs.getByText("Studio")).toHaveAttribute("aria-current", "page");

    for (const [old, now] of [["/studio", "/others/publishing/studio"], ["/calendar", "/others/publishing/calendar"], ["/automation", "/others/publishing/queue"],
      ["/publishing/connections", "/others/publishing/connections"]]) {
      await page.goto(old);
      await expect(page).toHaveURL(new RegExp(`${now}$`));
    }
    // Leaving the primary sidebar untouched by any of it.
    await expect(primary(page).getByRole("link")).toHaveCount(7);
  });

  test("Leads has Contacts and Lists as tabs under one entry", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/leads");
    const tabs = page.getByRole("navigation", { name: "Leads sections" });
    await expect(tabs.getByRole("link", { name: "Contacts" })).toHaveAttribute("aria-current", "page");
    await tabs.getByRole("link", { name: "Lists" }).click();
    await expect(page).toHaveURL(/\/leads\?tab=lists$/);
    await expect(tabs.getByRole("link", { name: "Lists" })).toHaveAttribute("aria-current", "page");
    await expect(primary(page).getByRole("link", { name: "Leads" })).toHaveAttribute("aria-current", "page");
    await page.goto("/lead-lists");
    await expect(page).toHaveURL(/\/leads\?tab=lists$/);
  });

  test("landmarks, skip link and a collapsible sidebar", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/dashboard");
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible();

    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main-content$/);

    const toggle = sidebar(page).getByRole("button", { name: "Collapse sidebar" });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const wide = (await sidebar(page).boundingBox())?.width ?? 0;
    await toggle.click();
    const collapsed = sidebar(page).getByRole("button", { name: "Expand sidebar" });
    await expect(collapsed).toHaveAttribute("aria-expanded", "false");
    await expect.poll(async () => (await sidebar(page).boundingBox())?.width ?? 999).toBeLessThan(wide);  // the width animates
    await expect(primary(page).getByRole("link", { name: "Inbox" })).toBeVisible();
    await collapsed.click();
  });

  test("on a phone the sidebar is a keyboard-operable drawer", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/dashboard");
    await expect(sidebar(page)).toBeHidden();
    const open = page.getByRole("button", { name: "Open navigation" });
    await open.click();
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer.getByRole("navigation", { name: "Primary" }).getByRole("link")).toHaveCount(7);
    await expect(drawer.getByRole("link", { name: "Dashboard", exact: true })).toHaveAttribute("aria-current", "page");
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(open).toBeFocused();

    await open.click();
    await drawer.getByRole("link", { name: "Campaigns" }).click();
    await expect(page).toHaveURL(/\/campaigns$/);
    await expect(drawer).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test.describe("dashboard", () => {
  test.setTimeout(60_000);

  test("with no sender account it leads to connecting one", async ({ page }) => {
    await mockApi(page, newApi());
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Get Synex working for you" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Connect LinkedIn account" })).toHaveAttribute("href", "/linkedin-accounts?connect=1");
    await expect(page.getByRole("region", { name: "Key metrics" })).toHaveCount(0);
  });

  test("without dashboard feeds it shows real campaign totals and says what is missing", async ({ page }) => {
    const api = newApi({
      accounts: [account("a1", "Ada Lovelace"), account("a2", "Grace Hopper", { status: "needs_reconnect" })],
      campaigns: [campaign("c1", "Q4 outreach"), campaign("c2", "Webinar invite", { accountId: "a2", stats: { totalLeads: 10, invitesSent: 8, connected: 3, replied: 1, interested: 1, messagesSent: 2, acceptanceRate: 37.5, replyRate: 12.5 } })],
    });
    await mockApi(page, api);
    await page.goto("/dashboard");

    const cards = page.getByRole("region", { name: "Key metrics" });
    const card = (label: string) => cards.locator("div", { has: page.getByText(label, { exact: true }) }).last();
    await expect(card("Connections accepted")).toContainText("15");
    await expect(card("Leads contacted")).toContainText("38");
    await expect(card("Replies")).toContainText("6");
    await expect(card("Interested leads")).toContainText("3");
    await expect(card("Interested leads answered")).toContainText("Not available yet");
    await expect(card("Median response time")).toContainText("Not available yet");
    await expect(cards.getByText("All-time totals from your campaigns.")).toBeVisible();

    await expect(page.getByText("Performance over time is not available yet.")).toBeVisible();
    await expect(page.getByRole("img", { name: /Area chart/ })).toHaveCount(0);

    const table = page.getByRole("table", { name: "Results for each sender account" });
    await expect(table.getByRole("row", { name: /Ada Lovelace/ })).toContainText("Connected");
    await expect(table.getByRole("row", { name: /Ada Lovelace/ })).toContainText("1"); // campaigns
    await expect(table.getByRole("row", { name: /Grace Hopper/ })).toContainText("Needs reconnect");
    await expect(table.getByRole("row", { name: /Ada Lovelace/ })).toContainText("Not available yet");
    await expect(page.getByText("Per-account results are not available yet.")).toBeVisible();

    // A date range cannot be answered from campaign totals, so nothing is invented.
    await page.getByLabel("Date range").selectOption("30d");
    await expect(card("Connections accepted")).toContainText("Not available yet");
    await expect(cards.getByText("Figures for a date range or a single account need a dashboard feed")).toBeVisible();
    await page.getByLabel("Date range").selectOption("all");
    await page.getByLabel("Campaign").selectOption("c2");
    await expect(card("Connections accepted")).toContainText("3");
  });

  test("with the dashboard feeds it shows live figures, a chart with a table, and a weekly or daily toggle", async ({ page }) => {
    const api = newApi({
      accounts: [account("a1", "Ada Lovelace")],
      campaigns: [campaign("c1", "Q4 outreach")],
      feeds: {
        summary: { connectionsAccepted: 21, leadsContacted: 60, replies: 9, interestedLeads: 4, interestedAnswered: 3, medianResponseSeconds: 7500 },
        series: { points: [{ date: "2026-11-02", requests: 20, accepted: 8, replies: 2 }, { date: "2026-11-09", requests: 25, accepted: 11, replies: 5 }] },
        accounts: [{ accountId: "a1", requestsSent: 45, acceptedPercent: 42, leadsContacted: 44, replyPercent: 15 }],
      },
    });
    await mockApi(page, api);
    await page.goto("/dashboard");

    const cards = page.getByRole("region", { name: "Key metrics" });
    await expect(cards).toContainText("21");
    await expect(cards).toContainText("60");
    await expect(cards).toContainText("3");
    await expect(cards).toContainText("2 h 5 min");
    await expect(cards.getByText("Not available yet", { exact: true })).toHaveCount(0);

    const chart = page.getByRole("img", { name: /Area chart of requests sent, accepted and replies by week/ });
    await expect(chart).toBeVisible();
    await page.getByText("View the data as a table").click();
    const data = page.getByRole("table", { name: "Requests sent, accepted and replies by week" });
    await expect(data.getByRole("row", { name: /Nov 9/ })).toContainText("25");

    await page.getByRole("button", { name: "Daily" }).click();
    await expect(page.getByRole("button", { name: "Daily" })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => calls(api, "/dashboard/timeseries").some((c) => c.query.includes("granularity=day"))).toBe(true);

    const row = page.getByRole("table", { name: "Results for each sender account" }).getByRole("row", { name: /Ada Lovelace/ });
    await expect(row).toContainText("45");
    await expect(row).toContainText("42%");
    await expect(row).toContainText("15%");

    await page.getByLabel("Date range").selectOption("7d");
    await expect.poll(() => calls(api, "/dashboard/summary").some((c) => c.query.includes("from="))).toBe(true);
  });

  test("a metric is never shown as zero when it is unknown", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")], campaigns: [] }));
    await page.goto("/dashboard");
    const cards = page.getByRole("region", { name: "Key metrics" });
    await expect(cards.getByText("Not available yet", { exact: true })).toHaveCount(2); // answered + median; campaign totals are a true zero
  });
});

test.describe("inbox", () => {
  test.setTimeout(60_000);

  test("with no sender account it leads to connecting one", async ({ page }) => {
    await mockApi(page, newApi());
    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: "Connect LinkedIn account to receive replies" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Connect LinkedIn account" })).toHaveAttribute("href", "/linkedin-accounts?connect=1");
  });

  test("with an account but no conversations it explains the inbox", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/inbox");
    await expect(page.getByText("No conversations yet")).toBeVisible();
    await expect(page.getByText("Conversations appear here once a lead replies to a campaign message.")).toBeVisible();
    await expect(page.getByRole("link", { name: "View campaigns" })).toBeVisible();
    await expect(page.getByText("Select a conversation to read it.")).toBeVisible();
  });

  test("lists conversations, filters them, opens a thread, and keeps replying switched off", async ({ page }) => {
    const api = newApi({
      accounts: [account("a1", "Ada Lovelace")],
      conversations: [conversation("k1", "Jane Doe"), conversation("k2", "Sam Lee", { unread: false, lastMessagePreview: "Not now" })],
      messages: [
        { id: "m1", direction: "outbound", body: "Hi Jane, thanks for connecting", sentAt: "2026-11-13T09:00:00Z", deliveryStatus: "sent" },
        { id: "m2", direction: "inbound", body: "Thanks, tell me more", sentAt: "2026-11-14T09:00:00Z", deliveryStatus: "sent" },
      ],
    });
    await mockApi(page, api);
    await page.goto("/inbox");
    const list = page.getByRole("list", { name: "Conversations" });
    await expect(list.getByRole("button")).toHaveCount(2);
    await expect(list.getByRole("button", { name: /Jane Doe/ })).toContainText("Unread");

    await page.getByLabel("Show").selectOption("interested");
    await expect.poll(() => calls(api, "/conversations").some((c) => c.query.includes("status=interested"))).toBe(true);
    await page.getByLabel("Show").selectOption("all");
    await page.getByLabel("Search conversations").fill("jane");
    await expect.poll(() => calls(api, "/conversations").some((c) => c.query.includes("search=jane"))).toBe(true);
    await page.getByLabel("Search conversations").fill("");

    await list.getByRole("button", { name: /Jane Doe/ }).click();
    await expect(list.getByRole("button", { name: /Jane Doe/ })).toHaveAttribute("aria-current", "true");
    const thread = page.getByRole("region", { name: "Conversation", exact: true });
    await expect(thread.getByRole("heading", { name: "Jane Doe" })).toBeVisible();
    await expect(thread.getByText("Hi Jane, thanks for connecting")).toBeVisible();
    await expect(thread.getByText("You ·")).toBeVisible();
    await expect(thread.getByText("Jane Doe ·")).toBeVisible();

    await expect(thread.getByLabel("Reply")).toBeDisabled();
    await expect(thread.getByRole("button", { name: /Send reply/ })).toBeDisabled();
    await thread.getByRole("button", { name: /Send reply/ }).locator("xpath=..").hover();
    await expect(page.getByRole("tooltip").first()).toContainText("Sending replies from the inbox comes next");
  });

  test("filters that match nothing offer a way back", async ({ page }) => {
    const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
    await mockApi(page, api);
    await page.goto("/inbox");
    await page.getByLabel("Search conversations").fill("nobody");
    await expect(page.getByText("No conversations match")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByLabel("Search conversations")).toHaveValue("");
  });
});

test.describe("campaigns", () => {
  test.setTimeout(60_000);

  test("with no sender account it leads to connecting one", async ({ page }) => {
    await mockApi(page, newApi());
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { name: "Connect LinkedIn account to run campaigns" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Connect LinkedIn account" })).toHaveAttribute("href", "/linkedin-accounts?connect=1");
  });

  test("with an account but no campaigns it explains what a campaign is", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { name: "No campaigns yet" })).toBeVisible();
    await expect(page.getByText("A campaign is a sequence of steps")).toBeVisible();
  });

  test("shows a table, and the new-campaign action is off with an honest reason", async ({ page }) => {
    await mockApi(page, newApi({
      accounts: [account("a1", "Ada Lovelace"), account("a2", "Grace Hopper")],
      campaigns: [campaign("c1", "Q4 outreach", { accountIds: ["a2"] })],
    }));
    await page.goto("/campaigns");
    const table = page.getByRole("table", { name: "Campaigns and their results" });
    await expect(table.getByRole("columnheader")).toHaveText(["Name", "Status", "Progress", "Sender accounts", "Leads", "Accepted %", "Reply %"]);
    const row = table.getByRole("row", { name: /Q4 outreach/ });
    await expect(row).toContainText("Active");
    await expect(row).toContainText("Ada Lovelace, Grace Hopper");
    await expect(row).toContainText("40");
    await expect(row).toContainText("40%");
    await expect(row).toContainText("17%");

    await expect(page.getByRole("button", { name: "New campaign" })).toBeDisabled();
    await page.getByRole("button", { name: "New campaign" }).locator("xpath=..").hover();
    await expect(page.getByRole("tooltip").first()).toContainText("Building campaigns comes next");
  });
});
