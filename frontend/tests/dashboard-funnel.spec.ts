import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, campaign, mockApi, newApi } from "./mock-api";

/* The dashboard funnel and the per-campaign table. The API is mocked. */

const open = async (page: Page, withFeeds = true) => {
  const api = newApi({
    accounts: [account("a1", "Ada Lovelace")],
    campaigns: [campaign("c1", "Q4 outreach")],
    feeds: withFeeds ? { summary: { connectionsAccepted: 12, leadsContacted: 30, replies: 5, interestedLeads: 2, interestedAnswered: 1, medianResponseSeconds: 3600 }, series: { points: [] }, accounts: [] } : {},
  });
  await mockApi(page, api);
  await page.goto("/dashboard");
  return api;
};

test("the funnel shows each stage with its count and its share of the step before, and the campaign table says no data instead of 0%", async ({ page }) => {
  await open(page);
  const stages = page.getByRole("list", { name: "Funnel stages" }).getByRole("listitem");
  await expect(stages).toHaveCount(5);
  await expect(stages.nth(1)).toContainText("Contacted");
  await expect(stages.nth(1)).toContainText("30 (75% of the step before)");
  await expect(stages.nth(4)).toContainText("Interested");
  await expect(page.getByRole("meter", { name: "Accepted: 12" })).toBeVisible();
  const table = page.getByRole("table", { name: "Results for each campaign" });
  await expect(table.getByRole("row", { name: /Q4 outreach/ })).toContainText("40%");
  await expect(table.getByRole("row", { name: /Quiet/ })).toContainText("No data");
});

test("the filters apply to the funnel too, and both exports download a file", async ({ page }) => {
  const api = await open(page);
  await page.getByLabel("Date range").selectOption("30d");
  await expect.poll(() => callsTo(api, "GET", /\/dashboard\/funnel$/).some((c) => c.query.includes("from="))).toBe(true);
  await page.locator("#filter-campaign").selectOption("c1");
  await expect.poll(() => callsTo(api, "GET", /\/dashboard\/campaigns$/).some((c) => c.query.includes("campaignId=c1"))).toBe(true);
  let download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("synex-timeseries.csv");
  download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export campaigns" }).click();
  expect((await download).suggestedFilename()).toBe("synex-campaigns.csv");
});

test("without a dashboard feed the funnel says so instead of showing numbers", async ({ page }) => {
  await open(page, false);
  await expect(page.getByText("The funnel needs a dashboard feed that is not available yet.")).toBeVisible();
});
