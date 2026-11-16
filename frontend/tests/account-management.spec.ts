import { test, expect } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* One sender account's own page: limits, privacy, health, lifecycle. The API is mocked; no LinkedIn is involved. */

const open = async (page: import("@playwright/test").Page, over: Record<string, unknown> = {}) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace", over)] });
  await mockApi(page, api);
  await page.goto("/linkedin-accounts");
  await page.getByRole("link", { name: /Manage Ada Lovelace/ }).click();
  return api;
};

test("the account page opens from the list and offers its four sections as tabs", async ({ page }) => {
  await open(page);
  await expect(page).toHaveURL(/\/linkedin-accounts\/a1$/);
  await expect(page.getByRole("heading", { name: "Ada Lovelace", level: 1 })).toBeVisible();
  const tabs = page.getByRole("tablist", { name: "Account sections" }).getByRole("tab");
  await expect(tabs).toHaveText(["Sender limits", "Inbox privacy", "Health", "Account"]);
  await expect(page.getByRole("tab", { name: "Sender limits" })).toHaveAttribute("aria-selected", "true");
  // Keyboard: arrows move between tabs, and the chosen tab is in the address so a refresh keeps it.
  await page.getByRole("tab", { name: "Sender limits" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Inbox privacy" })).toBeFocused();
  await expect(page).toHaveURL(/tab=privacy/);
  await page.reload();
  await expect(page.getByRole("tab", { name: "Inbox privacy" })).toHaveAttribute("aria-selected", "true");
});

test("a new account is offered recommended limits; applying them saves a policy under every hard maximum", async ({ page }) => {
  const api = await open(page);
  await expect(page.getByRole("heading", { name: "Recommended limits for a new account" })).toBeVisible();
  await page.getByRole("button", { name: "Show suggestions" }).click();
  await expect(page.getByText("Connection requests: start at 5 a day, growing to 25 (maximum 40).")).toBeVisible();
  await page.getByRole("button", { name: "Apply limits" }).click();
  await expect(page.getByText("Limits saved.")).toBeVisible();
  const saved = callsTo(api, "PUT", /\/policy$/)[0].body as { preset: string; actions: Record<string, { dailyLimit: number; stopAt: number }> };
  expect(saved.preset).toBe("conservative");
  expect(Object.keys(saved.actions)).toHaveLength(7);
  const ceilings: Record<string, number> = { send_invite: 40, send_message: 100, visit_profile: 80, follow_profile: 50, check_connection: 80, sync_inbox: 48, collect_leads: 20 };
  for (const [action, policy] of Object.entries(saved.actions)) {
    expect(policy.stopAt).toBeLessThanOrEqual(ceilings[action]);
    expect(policy.dailyLimit).toBeLessThanOrEqual(policy.stopAt);
  }
  await expect(page.getByRole("heading", { name: "Recommended limits for a new account" })).toBeHidden();
});

test("the limits table shows what was used, today's limit with its range, and the hard maximum for every action", async ({ page }) => {
  await open(page);
  const table = page.getByRole("table", { name: "Actions used in the last 24 hours against today's limits" });
  await expect(table.getByRole("columnheader")).toHaveText(["Action", "Used", "Today's limit", "Range", "Hard maximum"]);
  await expect(table.getByRole("row")).toHaveCount(8);
  await expect(table.getByRole("row", { name: /Connection requests/ })).toContainText("40");
  await expect(table.getByRole("row", { name: /Lead collection pages/ })).toContainText("20");
});

test("a limit cannot be typed above its hard maximum, presets lock the growth fields, and Custom unlocks them", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Keep current" }).click();
  const invites = page.getByLabel("Connection requests: daily limit");
  const stop = page.getByLabel(/Connection requests: stop at/);
  await stop.fill("90"); // the hard maximum is 40
  await expect(stop).toHaveValue("40");
  await invites.fill("100");
  await expect(invites).toHaveValue("40"); // never above its own stop value
  await page.getByLabel("Balanced").check();
  await expect(page.getByLabel("Connection requests: increase by")).toBeDisabled();
  await expect(page.getByLabel("Connection requests: increase by")).toHaveValue("2");
  await page.getByLabel("Custom").check();
  await expect(page.getByLabel("Connection requests: increase by")).toBeEnabled();
  await expect(page.getByText("You have unsaved changes.")).toBeVisible();
  await page.getByLabel("Daily variation").selectOption("3");
  await page.getByRole("button", { name: "Save limits" }).click();
  await expect(page.getByText("Limits saved.")).toBeVisible();
  const saved = callsTo(api, "PUT", /\/policy$/)[0].body as { preset: string; range: number };
  expect([saved.preset, saved.range]).toEqual(["custom", 3]);
  await expect(page.getByRole("button", { name: "Save limits" })).toBeDisabled();
});

test("a refused save keeps what was typed and says why", async ({ page }) => {
  const api = await open(page);
  api.policyStatus = 422;
  await page.getByRole("button", { name: "Keep current" }).click();
  await page.getByLabel("Aggressive").check();
  await page.getByRole("button", { name: "Save limits" }).click();
  await expect(page.getByText("Something went wrong").or(page.getByText(/above the maximum/))).toBeVisible();
  await expect(page.getByLabel("Aggressive")).toBeChecked();
});

test("inbox privacy: only the connecting person may change it, otherwise the page says so and locks the choices", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace", { canChangeSyncMode: false })], management: { a1: { policy: { preset: "off", range: 1, actions: {}, autoWithdraw: false, staleInviteDays: 30, inboxHistoryDays: 90 }, lifecycle: "active", canChangePrivacy: false } } });
  await mockApi(page, api);
  await page.goto("/linkedin-accounts/a1?tab=privacy");
  await expect(page.getByText(/Account access required/)).toBeVisible();
  await expect(page.getByLabel("All LinkedIn conversations")).toBeDisabled();
  await expect(page.getByLabel("Inbox history (days)")).toBeDisabled();
});

test("health: auto-withdraw can be switched on and saved, and the page is honest that nothing is withdrawn yet", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "Health" }).click();
  await expect(page.getByText(/withdrawing is not active yet/)).toBeVisible();
  await page.getByRole("switch", { name: "Auto-withdraw stale invitations" }).click();
  await expect(page.getByText("Health settings saved.")).toBeVisible();
  expect((callsTo(api, "PUT", /\/policy$/)[0].body as { autoWithdraw: boolean }).autoWithdraw).toBe(true);
  await expect(page.getByText(/No verified LinkedIn SSI data/)).toBeVisible();
});

test("account: deactivating asks first, then frees the seat and keeps the history", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "Account" }).click();
  await page.getByRole("button", { name: "Deactivate seat" }).click();
  const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog"));
  await expect(dialog.getByText(/History is kept/)).toBeVisible();
  await dialog.getByRole("button", { name: "Deactivate seat" }).click();
  await expect(page.getByText("Seat deactivated.")).toBeVisible();
  expect(callsTo(api, "POST", /\/deactivate$/)).toHaveLength(1);
  await expect(page.getByRole("button", { name: "Seat deactivated" })).toBeDisabled();
});

test("an unknown account shows a clear message and a way back", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.goto("/linkedin-accounts/nope");
  await expect(page.getByText(/not found|could not read/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "All sender accounts" })).toBeVisible();
});
