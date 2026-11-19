import { test, expect } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* Profile settings and the What's new list. The API is mocked. */

test("the profile saves name, company, designation and phone; the email cannot be changed here", async ({ page }) => {
  const api = newApi();
  await mockApi(page, api);
  await page.goto("/settings");
  await expect(page.getByRole("textbox", { name: "Email" })).toBeDisabled();
  await page.getByRole("textbox", { name: "Designation" }).fill("Founder");
  await page.getByRole("textbox", { name: "Phone" }).fill("+65 1234 5678");
  await page.getByRole("textbox", { name: "Company" }).fill("Engines");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Preferences saved")).toBeVisible();
  expect(callsTo(api, "PUT", /\/auth\/me$/)[0].body).toMatchObject({ company: "Engines", designation: "Founder", phone: "+65 1234 5678" });
});

test("What's new shows a dot until opened, lists the changes newest first, and opening it marks them read", async ({ page }) => {
  const api = newApi();
  api.assistant.unreadNews = true;
  await mockApi(page, api);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "What's new, unread" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { level: 3 })).toHaveText(["Smart sequences", "Earlier change"]);
  await expect.poll(() => callsTo(api, "POST", /whats-new\/seen$/).length).toBe(1);
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("button", { name: "What's new", exact: true })).toBeVisible();
});
