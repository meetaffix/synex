import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* The Safety page: the kill switch, the hard limits with the test profile, and the audit log. The API is mocked; nothing is sent. */

const row = (i: number, accountId = "a1") => ({ id: `r${i}`, accountId, at: `2026-11-16T10:${String(i % 60).padStart(2, "0")}:00Z`, account: accountId === "a1" ? "Ada Lovelace" : "Bo Sender",
  action: i % 2 ? "send_invite" : "send_message", result: i === 3 ? "profile_unavailable" : "sent", status: i === 3 ? "error" : "ok",
  reason: i === 3 ? "The profile could not be opened, so the person was skipped." : "Done.", person: `Person ${i}`, campaign: "Autumn outreach" });

const open = async (page: Page, over: (api: ReturnType<typeof newApi>) => void = () => undefined) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace"), account("a2", "Bo Sender")] });
  over(api);
  await mockApi(page, api);
  await page.goto("/settings/safety");
  await expect(page.getByRole("heading", { name: "Safety", level: 1 })).toBeVisible();
  return api;
};

test("someone who is not an administrator sees why the kill switch is not theirs, and the hard limits with the test profile", async ({ page }) => {
  await open(page);
  await expect(page.getByText("Only a platform administrator can use the kill switch.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop all sending now" })).toHaveCount(0);
  await expect(page.getByText("200 actions a day in total, and 150 connection requests in any seven days.")).toBeVisible();
  const table = page.getByRole("table", { name: "Hard daily limit and test profile for each action" });
  await expect(table.getByRole("row", { name: /Connection requests/ })).toContainText("405");
  await expect(table.getByRole("row", { name: /Profile follows/ })).toContainText("50stopped");
  await expect(table.getByRole("row")).toHaveCount(14);
});

test("an administrator stops and resumes all sending, each after a confirmation", async ({ page }) => {
  const api = await open(page, (a) => { a.assistant.admin = true; });
  await expect(page.getByText("Running: senders act within their limits.")).toBeVisible();
  await page.getByRole("button", { name: "Stop all sending now" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Stop all sending?" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(callsTo(api, "POST", /kill-switch$/)).toHaveLength(0);
  await page.getByRole("button", { name: "Stop all sending now" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Stop all sending" }).click();
  await expect(page.getByText("Stopped: nothing is sent.")).toBeVisible();
  expect(callsTo(api, "POST", /kill-switch$/)[0].body).toEqual({ enabled: true });
  await page.getByRole("button", { name: "Resume sending" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Resume sending" }).click();
  await expect(page.getByText("Running: senders act within their limits.")).toBeVisible();
});

test("the audit log lists each action with its outcome, pages through, filters by sender, and has an empty state", async ({ page }) => {
  await open(page, (a) => { a.assistant.audit = [...Array.from({ length: 30 }, (_, i) => row(i)), row(99, "a2")]; });
  const table = page.getByRole("table", { name: "Actions taken on LinkedIn" });
  await expect(table.getByRole("row")).toHaveCount(26);
  await expect(page.getByRole("status").filter({ hasText: "of 31" })).toHaveText("1 to 25 of 31");
  await expect(table.getByRole("row", { name: /Person 3/ })).toContainText("The profile could not be opened");
  await expect(page.getByRole("button", { name: "Newer" })).toBeDisabled();
  await page.getByRole("button", { name: "Older" }).click();
  await expect(page.getByRole("status").filter({ hasText: "of 31" })).toHaveText("26 to 31 of 31");
  await page.getByLabel("Sender").selectOption("a2");
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(table).toContainText("Bo Sender");
});

test("with no actions yet the log says so", async ({ page }) => {
  await open(page);
  await expect(page.getByText("No actions yet. Once a campaign runs, each action appears here.")).toBeVisible();
});

test("a sender's limits tab applies the test profile: 5, 5 and 5, everything else stopped", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
  await mockApi(page, api);
  await page.goto("/linkedin-accounts/a1?tab=limits");
  await page.getByRole("button", { name: "Apply the test profile" }).click();
  await expect(page.getByText("Limits saved.")).toBeVisible();
  const saved = callsTo(api, "PUT", /\/policy$/)[0].body as { actions: Record<string, { dailyLimit: number; stopAt: number }> };
  expect([saved.actions.visit_profile.stopAt, saved.actions.send_invite.stopAt, saved.actions.send_message.stopAt]).toEqual([5, 5, 5]);
  expect(saved.actions.like_post.dailyLimit).toBe(0);
  expect(saved.actions.send_inmail.stopAt).toBe(0);
});
