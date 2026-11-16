import { test, expect } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* The "How would you like to add leads?" dialog. The API is mocked; nothing is read from LinkedIn. */

const source = (page: import("@playwright/test").Page, text: RegExp | string) => page.getByRole("list", { name: "Lead sources" }).locator("button").filter({ hasText: text });

const open = async (page: import("@playwright/test").Page) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
  await mockApi(page, api);
  await page.goto("/leads");
  await page.getByRole("button", { name: /^Add leads?$/ }).first().click();
  return api;
};

test("every source is listed; the unbuilt one says Coming soon and cannot be chosen", async ({ page }) => {
  await open(page);
  const list = page.getByRole("list", { name: "Lead sources" });
  await expect(list.locator("button")).toHaveCount(9);
  await expect(source(page, /LinkedIn group members/)).toBeDisabled();
  await expect(list.getByText(/Coming soon: LinkedIn only shows/)).toBeVisible();
  await expect(list.getByText("Needs a Sales Navigator subscription on the sender account.")).toBeVisible();
});

test("an event: the hint warns about attending, the estimate shows before anything runs, and a wrong address is explained", async ({ page }) => {
  const api = await open(page);
  await source(page, /LinkedIn event attendees/).click();
  await expect(page.getByText(/must be marked as attending the event/).first()).toBeVisible();
  await expect(page.getByTestId("estimate")).toContainText("up to 50 people, about 15 page loads, around 5 minutes");
  await expect(page.getByTestId("estimate")).toContainText("at most 15 pages; run it again for more");
  await page.getByLabel("Links or data").fill("https://example.com/bad");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("alert")).toHaveText("Paste a LinkedIn event address (it contains linkedin.com/events/).");
  await page.getByLabel("Links or data").fill("https://www.linkedin.com/events/world-summit-123/");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("list", { name: "First people found" })).toContainText("Katherine Johnson", { timeout: 15000 });
  expect(callsTo(api, "POST", /\/lead-collections$/).length).toBe(2);
});

test("company sources say they make a list of companies and hide the people-only options", async ({ page }) => {
  await open(page);
  await source(page, /LinkedIn companies/).click();
  await expect(page.getByText(/makes a list of companies, not people/)).toBeVisible();
  await expect(page.getByText("People already contacted")).toHaveCount(0);
  await expect(page.getByLabel("Links or data")).toBeVisible();
});

test("a pasted-links source needs no sender and says nothing is read from LinkedIn", async ({ page }) => {
  await open(page);
  await expect(source(page, /Paste profile links/)).toContainText("Nothing is read from LinkedIn");
  await source(page, /Paste profile links/).click();
  await expect(page.getByLabel("Sender account (reads LinkedIn)")).toHaveCount(0);
  await expect(page.getByTestId("estimate")).toHaveCount(0);
});

test("the estimate says how many page reads the chosen account has left today", async ({ page }) => {
  await open(page);
  await source(page, /LinkedIn event attendees/).click();
  await expect(page.getByTestId("estimate")).toContainText("This account can read 12 more pages today.");
});

test("a CSV source offers a sample file and refuses a file over 5 MB with the fix", async ({ page }) => {
  await open(page);
  await source(page, /CSV or Google Sheets/).click();
  await expect(page.getByRole("link", { name: "Download a sample CSV" })).toHaveAttribute("download", "synex-sample-leads.csv");
  await page.getByLabel("CSV file").setInputFiles({ name: "big.csv", mimeType: "text/csv", buffer: Buffer.alloc(5_100_000, "a") });
  await expect(page.getByRole("alert")).toHaveText("That file is larger than 5 MB. Split it into smaller files.");
});
