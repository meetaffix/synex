import { test, expect } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* The do-not-contact list under Leads. The API is mocked. */

const open = async (page: import("@playwright/test").Page) => {
  const api = newApi();
  await mockApi(page, api);
  await page.goto("/leads?tab=dnc");
  return api;
};

test("the tab explains what the list does and starts empty for people and companies", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("tab", { name: "Do not contact" }).or(page.getByRole("link", { name: "Do not contact" }))).toBeVisible();
  await expect(page.getByText(/never starts a campaign/)).toBeVisible();
  await expect(page.getByText("No people on the list yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export" })).toBeDisabled();
  await page.getByRole("button", { name: "Companies" }).click();
  await expect(page.getByText("No companies on the list yet.")).toBeVisible();
});

test("profiles are added from pasted lines, the result is counted, search narrows, remove asks first", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Add profiles" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Add to list" })).toBeDisabled();
  await dialog.getByLabel("Profile links").fill("https://www.linkedin.com/in/ada-l/\nhttps://www.linkedin.com/in/grace-h/\nnot a link");
  await dialog.getByRole("button", { name: "Add to list" }).click();
  await expect(page.getByText("2 added, 0 already listed, 1 skipped as not a valid profile.")).toBeVisible();
  expect(callsTo(api, "POST", /\/do-not-contact$/)).toHaveLength(1);
  await expect(page.getByRole("row", { name: /ada-l/ })).toBeVisible();
  await page.getByLabel("Search").fill("grace");
  await expect(page.getByRole("row")).toHaveCount(2); // header and one match
  await page.getByLabel("Search").fill("");
  await page.getByRole("button", { name: /Remove https:\/\/www.linkedin.com\/in\/ada-l/ }).click();
  await expect(page.getByRole("alertdialog").or(page.getByRole("dialog")).getByText(/can be imported and contacted again/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText("Removed.")).toBeVisible();
  await expect(page.getByRole("row", { name: /ada-l/ })).toHaveCount(0);
});

test("companies are a separate list, and a CSV import and an export work", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Companies" }).click();
  await page.getByRole("button", { name: "Add companies" }).click();
  await page.getByRole("dialog").getByLabel("Companies").fill("Acme Inc\nGlobex Corp");
  await page.getByRole("dialog").getByRole("button", { name: "Add to list" }).click();
  await expect(page.getByText("2 added, 0 already listed, 0 skipped as not a valid company.")).toBeVisible();
  await expect(page.getByRole("row", { name: /Acme Inc/ })).toBeVisible();
  await page.getByLabel("Import a CSV with a company column").setInputFiles({ name: "c.csv", mimeType: "text/csv", buffer: Buffer.from("company\nInitech\n") });
  await expect(page.getByText(/1 added/)).toBeVisible();
  expect(callsTo(api, "POST", /\/do-not-contact\/import$/)).toHaveLength(1);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  expect((await download).suggestedFilename()).toBe("synex-do-not-contact-companies.csv");
  await page.getByRole("button", { name: "People" }).click();
  await expect(page.getByText("No people on the list yet.")).toBeVisible(); // lists do not mix
});
