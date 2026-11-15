import { test, expect } from "@playwright/test";
import { account, lead, mockApi, newApi } from "./mock-api";

/* The Contacts table at 1280: Name, Company, Email and Status always show; the rest is chosen and remembered. */

const api = () =>
  newApi({
    accounts: [account("a1", "Ada Lovelace")],
    leads: [lead("l1"), lead("l2", { firstName: "Sam", lastName: "Lee", company: "Acme", email: "sam@acme.example", location: "Leeds", phone: "+44 20 7946 0000", industry: "Software" })],
  });

const headers = (page: import("@playwright/test").Page) =>
  page.getByRole("region", { name: "Leads" }).getByRole("columnheader").allInnerTexts();

test("at 1280 the core columns show, extra columns are chosen, remembered, and scroll inside the table", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockApi(page, api());
  await page.goto("/leads");
  await expect(page.getByRole("region", { name: "Leads" })).toBeVisible();

  const shown = (await headers(page)).map((h) => h.trim()).filter(Boolean);
  expect(shown).toEqual(expect.arrayContaining(["Name", "Company", "Email", "Status"]));
  expect(shown).not.toContain("Location");
  expect(shown).not.toContain("Title");
  for (const name of ["Name", "Company", "Email", "Status"]) {
    await expect(page.getByRole("columnheader", { name })).toBeInViewport();
  }

  // Choose more columns.
  await page.getByRole("button", { name: "Columns" }).click();
  for (const column of ["Location", "Phone", "Industry"]) {
    await page.getByRole("menuitemcheckbox", { name: column }).click();
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("columnheader", { name: "Location" })).toBeAttached();
  await expect(page.getByRole("cell", { name: "Leeds" })).toBeAttached();
  // The core columns stay in view even with every extra column chosen.
  for (const name of ["Name", "Company", "Email", "Status"]) {
    await expect(page.getByRole("columnheader", { name })).toBeInViewport();
  }

  // More columns than fit: the table's own region scrolls sideways, the page does not.
  const fit = await page.evaluate(() => {
    const region = document.querySelector('[role="region"][aria-label="Leads"]') as HTMLElement;
    return { region: region.scrollWidth > region.clientWidth, page: document.documentElement.scrollWidth <= window.innerWidth };
  });
  expect(fit).toEqual({ region: true, page: true });

  // Remembered for this person after a reload.
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Location" })).toBeAttached();
  await page.getByRole("button", { name: "Columns" }).click();
  await expect(page.getByRole("menuitemcheckbox", { name: "Location" })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("menuitemcheckbox", { name: "Location" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("columnheader", { name: "Location" })).toHaveCount(0);

  const stored = await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith("synex.leads.columns.")));
  expect(stored).toEqual(["synex.leads.columns.u1"]); // keyed by the signed-in person
});
