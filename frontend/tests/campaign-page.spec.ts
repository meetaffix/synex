import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, campaign, mockApi, newApi } from "./mock-api";

/* A launched campaign has its own page: counts, what is happening, each lead's progress, the sequence, and Pause or Resume.
   The API is mocked; nothing is sent. */

const STEPS = [
  { id: "s1", type: "connection_request", order: 0, message: "Hi {{first_name}}", delayHours: null, aiConfig: null, parentStepId: null, branchCondition: null, config: null },
  { id: "s2", type: "wait", order: 1, message: null, delayHours: 48, aiConfig: null, parentStepId: null, branchCondition: null, config: null },
  { id: "s3", type: "message", order: 2, message: "Thanks for connecting", delayHours: null, aiConfig: null, parentStepId: null, branchCondition: null, config: null },
];
const full = (status: string) => ({
  ...campaign("c1", "Autumn outreach", { status }), description: null, leadListId: "L1", dailyConnectionLimit: 20, dailyMessageLimit: 40,
  schedule: { timezone: "Asia/Kolkata", days: [1], startHour: 9, endHour: 17 }, settings: { stopWhenReplied: true }, weekSchedule: null,
  exclusions: {}, allocation: {}, aiContext: {}, webhook: null, sequenceMode: "smart", steps: STEPS,
});
const monitor = {
  campaignId: "c1", status: "active", health: "attention", runCounts: { running: 1, completed: 1 },
  currentActions: [{ id: "t1", runId: "r1", type: "send_invite", status: "running", attempts: 1, leadName: "Ada Lovelace", error: null, updatedAt: "2026-11-20T09:00:00Z" }],
  lastExecuted: { id: "t0", runId: "r2", type: "send_message", status: "done", attempts: 1, leadName: "Bo Bee", error: null, updatedAt: "2026-11-20T08:00:00Z" },
  nextScheduled: { runId: "r1", leadId: "l1", leadName: "Ada Lovelace", stepOrder: 1, at: "2026-11-21T08:00:00Z" },
  failures: [{ id: "t9", runId: "r3", type: "send_invite", status: "failed", attempts: 3, leadName: "Cy Cee", error: "The profile could not be opened", updatedAt: "2026-11-20T07:00:00Z" }],
  failedRuns: [], accounts: [{ id: "a1", name: "Ada Lovelace", live: true, dailyActionsUsed: 3, dailyActionLimit: 20 }],
};
const RUNS = [
  { runId: "r1", leadId: "l1", leadName: "Ada Lovelace", headline: "Mathematician", status: "waiting_connection", stopReason: null, stepType: "wait", stepOrder: 1, nextActionAt: "2026-11-21T08:00:00Z" },
  { runId: "r2", leadId: "l2", leadName: "Bo Bee", headline: "", status: "stopped", stopReason: "replied", stepType: "message", stepOrder: 2, nextActionAt: null },
];

const open = async (page: Page, status = "active") => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], campaigns: [campaign("c1", "Autumn outreach", { status })] });
  await mockApi(page, api);
  await page.route(/\/campaigns\?id=c1&monitor=1/, (route) => route.fulfill({ json: monitor }));
  await page.route(/\/campaigns\?id=c1$/, (route) => route.fulfill({ json: full(status) }));
  await page.route(/\/campaigns\/c1\/runs$/, (route) => route.fulfill({ json: RUNS }));
  await page.goto("/campaigns/c1");
  await expect(page.getByRole("heading", { name: "Autumn outreach", level: 1 })).toBeVisible();
  return api;
};

test("the campaign list opens a launched campaign on its own page, and a draft in the builder", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], campaigns: [campaign("c1", "Autumn outreach", { status: "active" }), campaign("c3", "Fresh draft", { status: "draft" })] });
  await mockApi(page, api);
  await page.goto("/campaigns");
  await expect(page.getByRole("link", { name: "Autumn outreach" })).toHaveAttribute("href", "/campaigns/c1");
  await expect(page.getByRole("link", { name: "Fresh draft" })).toHaveAttribute("href", "/campaigns/c3/edit");
});

test("it shows the counts, what is happening now, the last and next action, and the sender's use today", async ({ page }) => {
  await open(page);
  await expect(page.getByText("Invites sent")).toBeVisible();
  await expect(page.getByText("Messages sent")).toBeVisible();
  await expect(page.getByText("Now: Connection request for Ada Lovelace")).toBeVisible();
  await expect(page.getByText(/Last: Message for Bo Bee \(done\)/)).toBeVisible();
  await expect(page.getByText(/Next: Ada Lovelace/)).toBeVisible();
  await expect(page.getByText("3 of 20 actions")).toBeVisible();
  await expect(page.getByText("Some actions need your attention.")).toBeVisible();
});

test("a failed action can be retried or skipped from the page", async ({ page }) => {
  const api = await open(page);
  const needs = page.getByRole("region", { name: "Needs attention" });
  await expect(needs).toContainText("Cy Cee: The profile could not be opened");
  await needs.getByRole("button", { name: "Retry" }).click();
  await expect.poll(() => callsTo(api, "POST", /^\/campaigns$/).map((c) => c.body)).toContainEqual({ action: "run", id: "c1", runId: "r3", runAction: "retry" });
});

test("the Leads tab shows each lead's step and status, and the Sequence tab shows the steps", async ({ page }) => {
  await open(page);
  await page.getByRole("tab", { name: "Leads" }).click();
  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Ada Lovelace/ })).toContainText("Waiting to connect");
  await expect(table.getByRole("row", { name: /Ada Lovelace/ })).toContainText("Mathematician");
  await expect(table.getByRole("row", { name: /Bo Bee/ })).toContainText("Replied");
  await page.getByRole("tab", { name: "Sequence" }).click();
  await expect(page.getByRole("list", { name: "Sequence steps" })).toContainText("Send connection request");
  await expect(page.getByRole("list", { name: "Sequence steps" })).toContainText("Send message");
});

test("Pause stops the campaign and a paused one offers Resume and Edit", async ({ page }) => {
  const api = await open(page);
  await expect(page.getByRole("link", { name: /Edit sequence/ })).toHaveAttribute("href", "/campaigns/c1/edit"); // a running sequence can be edited
  await page.getByRole("button", { name: "Pause" }).click();
  await expect.poll(() => callsTo(api, "POST", /^\/campaigns$/).map((c) => c.body)).toContainEqual({ action: "update", id: "c1", status: "paused" });
});

test("a paused campaign shows Resume and Edit sequence", async ({ page }) => {
  await open(page, "paused");
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Edit sequence/ })).toHaveAttribute("href", "/campaigns/c1/edit");
});
