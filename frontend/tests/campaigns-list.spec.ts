import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, campaign, mockApi, newApi } from "./mock-api";

/* The campaigns list: columns, filters, and the row menu. The API is mocked. */

const open = async (page: Page) => {
  const api = newApi({
    accounts: [account("a1", "Ada Lovelace"), account("a2", "Grace Hopper")],
    campaigns: [
      campaign("c1", "Autumn outreach", { status: "active" }),
      campaign("c2", "Webinar invite", { status: "paused", accountId: "a2", accountName: "Grace Hopper" }),
      campaign("c3", "Fresh draft", { status: "draft" }),
      campaign("c4", "Old push", { status: "archived", displayStatus: "archived" }),
    ],
  });
  await mockApi(page, api);
  await page.goto("/campaigns");
  return api;
};

test("the table has the report's columns, shows the status a person reads, and hides archived campaigns until asked", async ({ page }) => {
  await open(page);
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader")).toContainText(["Name", "Status", "Leads", "Accepted %", "Reply %", "Accounts", "Actions"]);
  await expect(table.getByRole("row", { name: /Autumn outreach/ })).toContainText("Running");
  await expect(table.getByRole("row", { name: /Webinar invite/ })).toContainText("Paused");
  await expect(table.getByRole("row", { name: /Fresh draft/ })).toContainText("Draft");
  await expect(table.getByRole("row", { name: /Old push/ })).toHaveCount(0);
  await page.getByLabel("Status").selectOption("archived");
  await expect(table.getByRole("row", { name: /Old push/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Autumn outreach/ })).toHaveCount(0);
});

test("the status filter offers every status of the report, and search and accounts narrow the list", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("table")).toBeVisible();
  const options = await page.getByLabel("Status").locator("option").allTextContents();
  expect(options).toEqual(["All statuses", "Draft", "Paused", "Queued", "Running", "No more pending actions", "Finished", "Failed", "Archived"]);
  await page.getByLabel("Search").fill("webinar");
  await expect(page.getByRole("row", { name: /Webinar invite/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Autumn outreach/ })).toHaveCount(0);
  await page.getByLabel("Search").fill("");
  await page.getByLabel("Accounts").selectOption("a2");
  await expect(page.getByRole("row", { name: /Webinar invite/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Autumn outreach/ })).toHaveCount(0);
  await page.getByLabel("Search").fill("zzz");
  await expect(page.getByText("No campaigns match.")).toBeVisible();
});

test("the row menu: a draft can be edited and cannot be archived", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "More actions for Fresh draft" }).click();
  await expect(page.getByRole("menuitem", { name: "Edit campaign" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Archive campaign" })).toHaveAttribute("aria-disabled", "true");
});

test("the row menu: duplicate makes a draft copy", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "More actions for Webinar invite" }).click();
  await page.getByRole("menuitem", { name: "Duplicate campaign" }).click();
  await expect(page.getByText("Campaign duplicated as a draft.")).toBeVisible();
  expect(callsTo(api, "POST", /^\/campaigns$/).some((c) => (c.body as { action?: string }).action === "duplicate")).toBe(true);
});

test("the row menu: a paused campaign can be archived and moves out of the default list", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "More actions for Webinar invite" }).click();
  await page.getByRole("menuitem", { name: "Archive campaign" }).click();
  await expect(page.getByText("Campaign archived.")).toBeVisible();
  await expect(page.getByRole("row", { name: /Webinar invite/ })).toHaveCount(0);
});

test("the row menu: share sequence downloads a file", async ({ page }) => {
  await open(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "More actions for Autumn outreach" }).click();
  await page.getByRole("menuitem", { name: "Share sequence" }).click();
  expect((await download).suggestedFilename()).toBe("autumn-outreach.synex-sequence.json");
});

test("the row menu: delete asks first, then removes the campaign", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "More actions for Autumn outreach" }).click();
  await page.getByRole("menuitem", { name: "Delete campaign" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Do you really want to delete Autumn outreach?")).toBeVisible();
  await dialog.getByRole("button", { name: "Delete campaign" }).click();
  await expect(page.getByText("Campaign deleted.")).toBeVisible();
  await expect(page.getByRole("row", { name: /Autumn outreach/ })).toHaveCount(0);
});

test("the empty list invites you to create the first campaign", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.goto("/campaigns");
  await expect(page.getByText("Ready to start your first campaign?")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your first campaign" })).toHaveAttribute("href", "/campaigns/new");
});
