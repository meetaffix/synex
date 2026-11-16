import { test, expect } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* Custom campaign variables on a lead, and company lists. The API is mocked. */

test("a lead can carry custom campaign variables; bad names are explained and block saving", async ({ page }) => {
  const api = newApi();
  await mockApi(page, api);
  await page.goto("/leads");
  await page.getByRole("button", { name: /^Add lead$/ }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name").fill("Ada");
  await dialog.getByLabel("Last name").fill("Lovelace");
  await expect(dialog.getByText(/Use one in a message as/)).toBeVisible();
  await dialog.getByRole("button", { name: "New variable" }).click();
  await dialog.getByLabel("Variable 1 name").fill("company");
  await expect(dialog.getByText("Synex already fills this one in. Choose another name.")).toBeVisible();
  await dialog.getByLabel("Variable 1 name").fill("1bad");
  await expect(dialog.getByText("Use letters, digits and underscores, starting with a letter.")).toBeVisible();
  await dialog.getByRole("button", { name: "Add lead" }).click();
  expect(callsTo(api, "POST", /^\/leads$/)).toHaveLength(0); // nothing was sent while a name is invalid
  await dialog.getByLabel("Variable 1 name").fill("eventName");
  await dialog.getByLabel("Variable 1 value").fill("SaaStr 2026");
  await dialog.getByRole("button", { name: "New variable" }).click();
  await dialog.getByLabel("Variable 2 name").fill("eventName");
  await expect(dialog.getByText("Each variable needs its own name.").first()).toBeVisible();
  await dialog.getByRole("button", { name: "Remove variable 2" }).click();
  await dialog.getByRole("button", { name: "Add lead" }).click();
  await expect(page.getByText("Lead created")).toBeVisible();
  const sent = callsTo(api, "POST", /^\/leads$/)[0].body as { variables: Record<string, string> };
  expect(sent.variables).toEqual({ eventName: "SaaStr 2026" });
});

test("company lists: empty state, view, add all to do-not-contact, delete with confirm", async ({ page }) => {
  const api = newApi();
  await mockApi(page, api);
  await page.goto("/leads?tab=companies");
  await expect(page.getByText(/No company lists yet/)).toBeVisible();
  api.companyLists = [{ id: "cl1", name: "SaaS companies", count: 2, createdAt: "2026-11-16T10:00:00Z" }];
  await page.reload();
  await expect(page.getByRole("heading", { name: "SaaS companies" })).toBeVisible();
  await page.getByRole("button", { name: "View" }).click();
  await expect(page.getByRole("link", { name: "Acme Inc" })).toBeVisible();
  await page.getByRole("button", { name: "Add all to do-not-contact" }).click();
  await expect(page.getByText("2 added to do-not-contact, 0 already listed.")).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete list" }).click();
  await expect(page.getByText("List deleted.")).toBeVisible();
  await expect(page.getByText(/No company lists yet/)).toBeVisible();
  expect(callsTo(api, "POST", /\/do-not-contact$/)).toHaveLength(1);
});
