import { test, expect } from "@playwright/test";
import { account, gate, mockApi, newApi } from "./mock-api";

/* The in-between states: what the person sees while a save or a proxy test is still running. */

test("the edit dialog shows that it is saving, locks its fields, then closes when the save lands", async ({ page }) => {
  const save = gate();
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], hold: { patch: save.promise } });
  await mockApi(page, api);
  await page.goto("/linkedin-accounts");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const limit = dialog.getByLabel("Daily action limit");
  await limit.fill("30");
  await dialog.getByRole("button", { name: "Save changes" }).click();

  // While the request is held: a spoken status, the fields locked, the submit button busy and not clickable twice.
  await expect(dialog.getByRole("status").filter({ hasText: "Saving changes…" })).toBeVisible();
  await expect(limit).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await expect(limit).toHaveValue("30"); // what the person typed is kept
  expect(api.calls.filter((c) => c.method === "PATCH")).toHaveLength(1);

  save.release();
  await expect(dialog).toBeHidden();
  expect(api.accounts[0].dailyActionLimit).toBe(30);
});

test("the proxy test shows that it is running, then its result", async ({ page }) => {
  const check = gate();
  await mockApi(page, newApi({ hold: { proxyTest: check.promise } }));
  await page.goto("/linkedin-accounts");
  await page.getByRole("button", { name: /^Connect (account|your first account)$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Advanced: proxy").click();
  await dialog.getByLabel("Paste a proxy URL").fill("socks5://user:pass@proxy.example.com:1080");
  await dialog.getByRole("button", { name: "Test connection" }).click();

  await expect(dialog.getByRole("status").filter({ hasText: "Testing the proxy. This can take up to 10 seconds." })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Test connection" })).toBeDisabled();

  check.release();
  await expect(dialog.getByRole("status").filter({ hasText: "Proxy works." })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Test connection" })).toBeEnabled();
});
