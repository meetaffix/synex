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
  await expect(page.getByText(/Connected since/)).toBeVisible();
  const tabs = page.getByRole("tablist", { name: "Account sections" }).getByRole("tab");
  await expect(tabs).toHaveText(["Sender limits", "Inbox privacy", "Health", "Manage connections", "AI configuration", "Account"]);
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
  expect(Object.keys(saved.actions)).toHaveLength(13);
  const ceilings: Record<string, number> = { send_invite: 40, send_message: 100, visit_profile: 80, follow_profile: 50, check_connection: 80, sync_inbox: 48, sync_connections: 12, collect_leads: 20, withdraw_invite: 20, like_post: 30, send_inmail: 15, send_voice_note: 20, engage_post: 25 };
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
  await expect(table.getByRole("row")).toHaveCount(14);
  await expect(table.getByRole("row", { name: /Connection requests/ })).toContainText("40");
  await expect(table.getByRole("row", { name: /Lead collection pages/ })).toContainText("20");
});

test("a limit cannot be typed above its hard maximum, presets lock the growth fields, and Custom unlocks them", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Keep current" }).click();
  await page.getByText("Advanced: set every action yourself").click();
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
  await page.getByText("Advanced: set every action yourself").click();
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

test("health: auto-withdraw can be switched on and saved, and the page says what it needs", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "Health" }).click();
  await expect(page.getByText(/not yet verified on real LinkedIn/)).toBeVisible();
  await page.getByRole("switch", { name: "Auto-withdraw stale invitations" }).click();
  await expect(page.getByText("Health settings saved.")).toBeVisible();
  expect((callsTo(api, "PUT", /\/policy$/)[0].body as { autoWithdraw: boolean }).autoWithdraw).toBe(true);
  await expect(page.getByText(/No verified LinkedIn SSI data/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Health summary" })).toBeVisible();
  await expect(page.getByText(/No warning or restriction has been recorded/)).toBeVisible();
  await expect(page.getByText("No activity has been recorded for this account yet.")).toBeVisible();
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

const person = (n: string, over: Record<string, string> = {}) => ({ id: n, name: n, headline: `${n} headline`, location: "London", profileUrl: `https://www.linkedin.com/in/${n.toLowerCase().replace(/ /g, "-")}/`, source: "sync", ...over });

test("manage connections: lists, searches and switches to received invitations", async ({ page }) => {
  const api = await open(page);
  api.connections.a1 = { connection: [person("Ada Lovelace"), person("Grace Hopper", { location: "New York" })], invitation: [person("Katherine Johnson")] };
  await page.getByRole("tab", { name: "Manage connections" }).click();
  await expect(page).toHaveURL(/tab=connections/);
  await expect(page.getByText(/a little at a time/)).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(3);
  await page.getByLabel("Search").fill("york");
  await expect(page.getByRole("row", { name: /Grace Hopper/ })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(2);
  await page.getByLabel("Search").fill("zzz");
  await expect(page.getByText("No one matches that search.")).toBeVisible();
  await page.getByLabel("Search").fill("");
  await page.getByRole("button", { name: "Received invitations" }).click();
  await expect(page.getByRole("link", { name: "Katherine Johnson" })).toBeVisible();
});

test("manage connections: an empty list explains how to fill it, and reload queues one gradual read", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "Manage connections" }).click();
  await expect(page.getByText(/Nothing stored yet/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  await page.getByRole("button", { name: "Reload connections" }).click();
  await expect(page.getByText("Reading connections has been queued.")).toBeVisible();
  expect(callsTo(api, "POST", /\/connections\/reload$/)).toHaveLength(1);
  await expect(page.getByRole("button", { name: "Reading" })).toBeDisabled();
  await expect(page.getByText("Synex is reading this list now.")).toBeVisible();
});

test("manage connections: a CSV is uploaded and the result counts are shown; export downloads a file", async ({ page }) => {
  const api = await open(page);
  api.connections.a1 = { connection: [person("Ada Lovelace")], invitation: [] };
  await page.getByRole("tab", { name: "Manage connections" }).click();
  await page.getByLabel("Upload a CSV with a linkedin_url column").setInputFiles({ name: "people.csv", mimeType: "text/csv", buffer: Buffer.from("linkedin_url\nhttps://www.linkedin.com/in/new-person/\nnot a url\n") });
  await expect(page.getByText(/1 added, 0 already stored, 0 repeated in the file, 1 skipped/)).toBeVisible();
  expect(callsTo(api, "POST", /\/connections\/import$/)).toHaveLength(1);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("synex-connections.csv");
});

test("manage connections: a stopped seat cannot start a new read", async ({ page }) => {
  await open(page);
  await page.getByRole("tab", { name: "Account" }).click();
  await page.getByRole("button", { name: "Deactivate seat" }).click();
  await page.getByRole("alertdialog").or(page.getByRole("dialog")).getByRole("button", { name: "Deactivate seat" }).click();
  await expect(page.getByText("Seat deactivated.")).toBeVisible();
  await page.getByRole("tab", { name: "Manage connections" }).click();
  await expect(page.getByRole("button", { name: "Reload connections" })).toBeDisabled();
});

test("account: delete needs the exact name typed, then removes the account and returns to the list", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "Account" }).click();
  await page.getByRole("button", { name: "Delete account" }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: "Delete permanently" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Account name").fill("ada lovelace");
  await expect(confirm).toBeDisabled(); // the name must match exactly
  await dialog.getByLabel("Account name").fill("Ada Lovelace");
  await confirm.click();
  await expect(page).toHaveURL(/\/linkedin-accounts$/);
  expect((callsTo(api, "POST", /\/delete$/)[0].body as { confirm: string }).confirm).toBe("Ada Lovelace");
  await expect(page.getByRole("heading", { name: "Ada Lovelace" })).toHaveCount(0);
});

test("inbox privacy: someone without access can send the owner a link", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace", { canChangeSyncMode: false })], management: { a1: { policy: { preset: "off", range: 1, actions: {}, autoWithdraw: false, staleInviteDays: 30, inboxHistoryDays: 90 }, lifecycle: "active", canChangePrivacy: false } } });
  await mockApi(page, api);
  await page.goto("/linkedin-accounts/a1?tab=privacy");
  await page.getByRole("button", { name: "Share with account owner" }).click();
  await expect(page.getByRole("dialog").getByText(/Reconnect link for Ada Lovelace/)).toBeVisible();
  expect(callsTo(api, "POST", /\/reconnect-link$/)).toHaveLength(1);
});

test("AI configuration: a preset voice is assigned with its licence shown; cloning is disabled with the reason", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("tab", { name: "AI configuration" }).click();
  await expect(page.getByTestId("assigned-voice")).toContainText("No voice assigned");
  await expect(page.getByRole("button", { name: "Clone my voice (coming soon)" })).toBeDisabled();
  await expect(page.getByText(/commercial licence/).first()).toBeVisible();
  await page.getByRole("button", { name: "Assign voice" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Licence: CC BY 4.0")).toBeVisible();
  await expect(dialog.getByText(/Piper\) is not installed/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Play a sample of Cori" })).toBeDisabled();
  await expect(dialog.getByText(/English \(India\) \(unavailable/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Select voice" })).toBeDisabled();
  await dialog.getByRole("radio", { name: "Cori" }).check();
  await dialog.getByRole("button", { name: "Select voice" }).click();
  await expect(page.getByText("Voice assigned.")).toBeVisible();
  expect((callsTo(api, "PUT", /\/voice$/)[0].body as { voiceId: string }).voiceId).toBe("cori");
  await expect(page.getByTestId("assigned-voice")).toContainText("Cori (English (UK), Female)");
  await page.getByRole("button", { name: "Remove voice" }).click();
  await expect(page.getByTestId("assigned-voice")).toContainText("No voice assigned");
});

test("keyboard only: tabs by arrow keys, a limit changed and saved, and the delete dialog traps focus and returns it on Escape", async ({ page }) => {
  const api = await open(page);
  // Every stop on the way is a real control with a name, and Tab reaches the limits form and its Save button.
  await page.getByText("Advanced: set every action yourself").click();
  await page.getByRole("tab", { name: "Sender limits" }).focus();
  const stops: string[] = [];
  for (let i = 0; i < 80 && !stops.some((s) => /Connection requests: daily limit/.test(s)); i++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el ? (el.getAttribute("aria-label") || el.textContent || el.getAttribute("name") || el.tagName).trim().slice(0, 60) : "";
    });
    stops.push(name);
  }
  expect(stops.some((s) => /Connection requests: daily limit/.test(s))).toBe(true);
  expect(stops.every((s) => s.length > 0)).toBe(true); // every stop is a named control
  expect(await page.evaluate(() => [...document.querySelectorAll("[tabindex]")].filter((e) => Number(e.getAttribute("tabindex")) > 0).length)).toBe(0);
  // Change a limit with the keyboard alone and save it with Enter.
  const daily = page.getByLabel("Connection requests: daily limit");
  await daily.focus();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("7");
  await page.getByRole("button", { name: "Save limits" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Limits saved.")).toBeVisible();
  const saved = callsTo(api, "PUT", /\/policy$/)[0].body as { actions: Record<string, { dailyLimit: number }> };
  expect(saved.actions.send_invite.dailyLimit).toBe(7);
  // Arrow keys reach the last tab; its Delete button opens a dialog that keeps focus inside and gives it back on Escape.
  await page.getByRole("tab", { name: "Sender limits" }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "Account" })).toHaveAttribute("aria-selected", "true");
  const trigger = page.getByRole("button", { name: "Delete account" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("the account header shows the name, headline, company and location read from the profile, and leaves them out when LinkedIn gave none", async ({ page }) => {
  await open(page, { company: "Analytical Engines", location: "London, United Kingdom" });
  await expect(page.getByRole("heading", { name: "Ada Lovelace", level: 1 })).toBeVisible();
  await expect(page.getByText("Engineer at Analytical Engines").first()).toBeVisible();
  await expect(page.getByTestId("account-place")).toHaveText("Analytical Engines · London, United Kingdom");
  await page.goto("/linkedin-accounts");
  await page.getByRole("link", { name: /Manage Ada Lovelace/ }).first().click();
});

test("with no company or location the header shows no empty place line", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "Ada Lovelace", level: 1 })).toBeVisible();
  await expect(page.getByTestId("account-place")).toHaveCount(0);
});
