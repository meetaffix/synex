import { test, expect, type Page } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* Settings and integrations. The API is mocked; nothing is sent anywhere. */

const open = async (page: Page, tab = "notifications") => {
  const api = newApi({ lists: [{ id: "L1", name: "Prospects", leadCount: 3, description: null, color: "primary", createdAt: "2026-11-01T00:00:00Z" }] as never });
  await mockApi(page, api);
  await page.goto(`/settings/integrations?tab=${tab}`);
  await page.waitForLoadState("networkidle");
  return api;
};

test("it has all eight sections as tabs and keeps the chosen one in the address", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("tab")).toHaveText(["Notifications", "Webhooks and Slack", "API and MCP", "Email tools", "HubSpot", "Import", "Usage", "Support"]);
  await page.getByRole("tab", { name: "Usage" }).click();
  await expect(page).toHaveURL(/tab=usage/);
  await expect(page.getByText(/not a balance/)).toBeVisible();
  await expect(page.getByText("send invite: 3")).toBeVisible();
});

test("notifications: change who and what, save, send a test, and see it in the outbox", async ({ page }) => {
  const api = await open(page);
  await expect(page.getByLabel("Email addresses (separate with commas)")).toHaveValue("boss@example.com");
  await page.getByRole("switch", { name: "Any message from a lead" }).click();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Notification settings saved.")).toBeVisible();
  expect((callsTo(api, "PUT", /notifications$/)[0].body as { reply_received: boolean }).reply_received).toBe(true);
  await page.getByRole("button", { name: "Send a test email" }).click();
  await expect(page.getByRole("list", { name: "Recent emails" })).toContainText("Synex: test notification to boss@example.com");
});

test("webhooks: a private address is refused with the reason, a good one shows its signing secret once, test and log work, Slack is its own type", async ({ page }) => {
  await open(page, "webhooks");
  await page.getByLabel("Webhook address").fill("http://localhost:9/x");
  await page.getByRole("button", { name: "Add webhook" }).click();
  await expect(page.getByText("That address points to a private network, which Synex will not call.")).toBeVisible();
  await page.getByLabel("Webhook address").fill("https://example.com/hook");
  await page.getByRole("button", { name: "Add webhook" }).click();
  await expect(page.getByText(/Signing secret/)).toContainText("whsec_SECRET123");
  const hook = page.getByRole("list", { name: "Webhooks" }).getByRole("listitem").first();
  await hook.getByRole("button", { name: "Send test" }).click();
  await expect(page.getByText("The receiver answered 500.")).toBeVisible();
  await hook.getByRole("button", { name: "Delivery log" }).click();
  await expect(hook.getByRole("list", { name: "Deliveries" })).toContainText("failed (500)");
  await page.getByLabel("Type").selectOption("slack");
  await expect(page.getByLabel("Slack webhook address")).toBeVisible();
});

test("API keys: the key is shown once, listed only by its prefix, and can be revoked; the page explains the API and MCP", async ({ page }) => {
  await open(page, "api");
  await page.getByLabel("Key name").fill("My CRM");
  await page.getByRole("button", { name: "Create key" }).click();
  await expect(page.getByText(/shown only once/)).toContainText("syx_abcdefgh_THE_WHOLE_KEY");
  const row = page.getByRole("list", { name: "API keys" }).getByRole("listitem").first();
  await expect(row).toContainText("My CRM");
  await expect(row).not.toContainText("THE_WHOLE_KEY");
  await expect(page.getByText(/Tools that change data are not offered/)).toBeVisible();
  await row.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("Key revoked.")).toBeVisible();
});

test("email tool exports, the importer, HubSpot and support each do their one job", async ({ page }) => {
  const api = await open(page, "email");
  await page.getByLabel("Lead list").selectOption("L1");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download for Smartlead" }).click();
  expect((await download).suggestedFilename()).toBe("synex-smartlead.csv");
  await page.getByRole("tab", { name: "Import" }).click();
  await page.getByLabel("CSV file").setInputFiles({ name: "x.csv", mimeType: "text/csv", buffer: Buffer.from("Profile URL,Campaign\nhttps://www.linkedin.com/in/a/,Spring\n") });
  await page.getByRole("button", { name: "Import leads" }).click();
  await expect(page.getByText(/2 added, 1 already known, 1 without a profile link/)).toBeVisible();
  await page.getByRole("tab", { name: "HubSpot" }).click();
  await expect(page.getByText(/not verified against a real HubSpot account/)).toBeVisible();
  await page.getByLabel("Private app token").fill("pat-na1-0123456789");
  await page.getByRole("button", { name: "Connect HubSpot" }).click();
  await page.getByRole("button", { name: "Import contacts" }).click();
  await expect(page.getByText("2 contacts added, 1 skipped for having no LinkedIn address.")).toBeVisible();
  await page.getByRole("tab", { name: "Support" }).click();
  await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
  await page.getByLabel("Subject").fill("Help please");
  await page.getByLabel("Message").fill("My account is stuck at login.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Your message is saved in this workspace.")).toBeVisible();
  expect(callsTo(api, "POST", /\/support$/)).toHaveLength(1);
});
