import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, inboxItem, mockApi, newApi } from "./mock-api";

/* The unified inbox. The API is mocked; nothing is sent to LinkedIn. */

const messages = [
  { id: "m1", direction: "outbound", body: "Hi Ann, I came across your work.", sentAt: "2026-11-15T09:00:00Z", deliveryStatus: "sent" },
  { id: "m2", direction: "inbound", body: "Sounds interesting, tell me more", sentAt: "2026-11-16T08:00:00Z", deliveryStatus: "sent" },
];

const open = async (page: Page, over: Parameters<typeof newApi>[0] = {}) => {
  const api = newApi({
    accounts: [account("a1", "Ada Lovelace"), account("a2", "Grace Hopper")],
    inbox: [
      inboxItem("c1", "Ann Archer", { unread: true, tags: ["warm"] }),
      inboxItem("c2", "Bob Baker", { starred: true, lastDirection: "outbound", needsReply: false, accountId: "a2", accountName: "Grace Hopper", unread: false }),
      inboxItem("c3", "Cy Clark", { status: "archived", needsReply: false }),
    ],
    messages,
    ...over,
  });
  await mockApi(page, api);
  await page.goto("/inbox");
  await expect(page.getByRole("list", { name: "Conversations" })).toBeVisible();
  return api;
};
const names = (page: Page) => page.getByRole("list", { name: "Conversations" }).getByRole("listitem");

test("the list shows each conversation's account, what it needs and its tags, archived ones are hidden, and nothing is selected at first", async ({ page }) => {
  await open(page);
  await expect(names(page)).toHaveCount(2);
  await expect(names(page).filter({ hasText: "Ann Archer" })).toContainText("Received by Ada Lovelace");
  await expect(names(page).filter({ hasText: "Ann Archer" })).toContainText("Needs reply");
  await expect(names(page).filter({ hasText: "Ann Archer" })).toContainText("warm");
  await expect(page.getByText("Select a conversation")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: /Last read/ })).toBeVisible();
});

test("filters: quick buttons, status, tag, interest and archived each change the list; Clear filters restores it", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Filters" }).click();
  const panel = page.getByRole("region", { name: "Filter conversations" });
  await panel.getByRole("button", { name: "Needs my reply" }).click();
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Ann Archer");
  await panel.getByRole("button", { name: "I messaged last" }).click();
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Bob Baker");
  await panel.getByRole("button", { name: "I messaged last" }).click();
  await panel.getByLabel("Starred").check();
  await expect(names(page)).toHaveCount(1);
  await panel.getByLabel("Starred").uncheck();
  await panel.getByLabel("Tag").selectOption("warm");
  await expect(names(page).first()).toContainText("Ann Archer");
  await panel.getByLabel("Tag").selectOption("");
  await panel.getByLabel("Archived").check();
  await expect(names(page).first()).toContainText("Cy Clark");
  await panel.getByRole("button", { name: "Clear filters" }).click();
  await expect(names(page)).toHaveCount(2);
  const sections = await panel.locator("legend").allTextContents();
  expect(sections).toEqual(["Status", "Sender accounts", "Campaigns"]);
  const presets = await panel.getByLabel("Date").locator("option").allTextContents();
  expect(presets).toEqual(["Any time", "Today", "Yesterday", "Last week", "Last month", "Last quarter", "Custom range"]);
});

test("the account chips filter to one sender, search narrows by name, and an empty result offers Clear filters", async ({ page }) => {
  await open(page);
  await page.getByRole("group", { name: "Sender accounts" }).getByRole("button", { name: "Grace Hopper" }).click();
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Bob Baker");
  await page.getByRole("button", { name: "All accounts" }).click();
  await page.getByLabel("Search all conversations").fill("zzz");
  await expect(page.getByText("No conversations match")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await expect(names(page)).toHaveCount(2);
});

test("a custom date range shows From and To fields", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Filters" }).click();
  await page.getByLabel("Date").selectOption("custom");
  await expect(page.getByLabel("From")).toBeVisible();
  await expect(page.getByLabel("To")).toBeVisible();
});

test("star from the row; select several to see the bulk bar, tag them and set an interest label", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Star Ann Archer" }).click();
  await expect.poll(() => callsTo(api, "POST", /\/inbox\/bulk$/).some((c) => (c.body as { action: string }).action === "star")).toBe(true);
  await page.getByLabel("Select Ann Archer").check();
  await page.getByLabel("Select Bob Baker").check();
  const bar = page.getByRole("toolbar", { name: "Bulk actions" });
  await expect(bar).toContainText("2 selected");
  await bar.getByLabel("Tag for the selected").fill("hot");
  await bar.getByRole("button", { name: "Add tag" }).click();
  await expect(page.getByText("Updated.")).toBeVisible();
  const tagCall = callsTo(api, "POST", /\/inbox\/bulk$/).find((c) => (c.body as { action: string }).action === "tag_add")!.body as { ids: string[]; value: string };
  expect([tagCall.ids.length, tagCall.value]).toEqual([2, "hot"]);
  await page.getByLabel("Select Ann Archer").check();
  await page.getByRole("toolbar", { name: "Bulk actions" }).getByRole("button", { name: "Archive" }).click();
  await expect.poll(() => callsTo(api, "POST", /\/inbox\/bulk$/).some((c) => (c.body as { action: string }).action === "archive")).toBe(true);
});

test("opening a thread reads it, shows date separators, and the profile panel offers star, answered, archive, interest and tags", async ({ page }) => {
  const api = await open(page);
  await names(page).filter({ hasText: "Ann Archer" }).getByRole("button", { name: /Ann Archer/ }).first().click();
  await expect(page.getByRole("heading", { name: "Ann Archer", level: 2 }).first()).toBeVisible();
  await expect(page.getByText("Sounds interesting, tell me more").first()).toBeVisible();
  await expect(page.getByText(/Sunday, Nov 15|Monday, Nov 16|Saturday, Nov 14/).first()).toBeVisible();
  expect(callsTo(api, "POST", /\/inbox\/bulk$/).some((c) => (c.body as { action: string }).action === "read")).toBe(true);
  const profile = page.getByRole("complementary", { name: "Profile details" });
  await expect(profile.getByRole("button", { name: "Fetch profile (coming soon)" })).toBeDisabled();
  await profile.getByRole("button", { name: "Mark as answered" }).click();
  await profile.getByLabel("Interest").selectOption("meeting_booked");
  await profile.getByPlaceholder("New tag").fill("vip");
  await profile.getByRole("button", { name: "Add tag" }).click();
  await expect(profile.getByText("Lead not present in any campaign.")).toBeVisible();
  const actions = callsTo(api, "POST", /\/inbox\/bulk$/).map((c) => (c.body as { action: string }).action);
  expect(actions).toEqual(expect.arrayContaining(["answered", "interest", "tag_add"]));
});

test("reply: a draft is saved as you type, Send queues the reply and says it is within the sender's limits", async ({ page }) => {
  const api = await open(page);
  await names(page).first().getByRole("button", { name: /Ann Archer/ }).first().click();
  const box = page.getByLabel("Reply", { exact: true });
  await box.fill("Happy to share more.");
  await expect.poll(() => callsTo(api, "PUT", /\/inbox\/c1\/draft$/).length, { timeout: 5000 }).toBeGreaterThan(0);
  await expect(page.getByText(/Sending from Ada Lovelace/)).toBeVisible();
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText(/Reply queued/)).toBeVisible();
  expect((callsTo(api, "POST", /^\/conversations$/)[0].body as { body: string }).body).toBe("Happy to share more.");
});

test("a suggested reply shows its cost before it is written, fills the box, and sends nothing", async ({ page }) => {
  const api = await open(page);
  await names(page).first().getByRole("button", { name: /Ann Archer/ }).first().click();
  await expect(page.getByText(/A suggested reply is written by template and costs nothing/)).toBeVisible();
  await page.getByRole("button", { name: "Suggest a reply" }).click();
  await expect(page.getByLabel("Reply", { exact: true })).toHaveValue(/Happy to share more/);
  expect(callsTo(api, "POST", /^\/conversations$/)).toHaveLength(0);
});

test("scheduling a message lists it and can cancel it; attachments and voice are disabled as coming soon", async ({ page }) => {
  const api = await open(page);
  await names(page).first().getByRole("button", { name: /Ann Archer/ }).first().click();
  await expect(page.getByRole("button", { name: "Attach (coming soon)" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Voice message (coming soon)" })).toBeDisabled();
  await page.getByLabel("Reply", { exact: true }).fill("See you Thursday");
  await page.getByRole("button", { name: "Schedule message" }).first().click();
  await page.getByLabel("Send at").fill("2099-01-01T10:00");
  await page.getByRole("button", { name: "Schedule message" }).first().click(); // the submit sits above the toggle once the form is open
  await expect(page.getByText("Message scheduled.")).toBeVisible();
  await expect(page.getByRole("list", { name: "Scheduled messages" })).toContainText("See you Thursday");
  expect((callsTo(api, "POST", /\/inbox\/c1\/schedule$/)[0].body as { sendAt: string }).sendAt).toMatch(/^2099-01-01T/);
  await page.getByRole("list", { name: "Scheduled messages" }).getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("list", { name: "Scheduled messages" })).toHaveCount(0);
});

test("Refresh reads the inboxes and says so, and Export CSV downloads the current view", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByText(/Reading 1 inbox/)).toBeVisible();
  expect(callsTo(api, "POST", /\/inbox\/refresh$/)).toHaveLength(1);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("synex-inbox.csv");
});

test("a conversation with no sender account is read-only and says so; with no conversations the page explains how they arrive", async ({ page }) => {
  await open(page, { inbox: [inboxItem("c9", "Dee Dunn", { accountId: null, accountName: null })] });
  await names(page).first().getByRole("button", { name: /Dee Dunn/ }).first().click();
  await expect(page.getByText(/Replies are disabled for this read-only conversation/)).toBeVisible();
  const empty = await page.context().newPage();
  await mockApi(empty, newApi({ accounts: [account("a1", "Ada Lovelace")], inbox: [] }));
  await empty.goto("/inbox");
  await expect(empty.getByText("No conversations yet")).toBeVisible();
});

test("an empty inbox on an account that keeps only Synex conversations says so, how many were left out, and where to change it", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")], inbox: [] }));
  await page.route(/\/inbox\/meta$/, (route) => route.fulfill({ json: { accounts: [{ id: "a1", name: "Ada Lovelace", lastSyncedAt: "2026-11-20T09:00:00Z", live: true, syncMode: "synex_only", lastSkipped: 4 }], campaigns: [], tags: [], interests: [] } }));
  await page.goto("/inbox");
  const note = page.getByRole("note").filter({ hasText: "keeps only conversations with people Synex has contacted" });
  await expect(note).toContainText("4 other conversations on LinkedIn are not shown");
  await expect(note.getByRole("link", { name: "change its conversation sync" })).toHaveAttribute("href", "/linkedin-accounts/a1");
});
