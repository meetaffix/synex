import { test, expect } from "@playwright/test";

test("manual CRM, preferences, calendar controls and sign-out persist", async ({
  page,
}) => {
  const tag = Date.now().toString(36);
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-Test-Password!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /^Good (morning|afternoon|evening)/, level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await page.goto("/settings");
  await page.getByLabel("Time zone", { exact: true }).fill("Europe/Amsterdam");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Preferences saved")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Time zone", { exact: true })).toHaveValue(
    "Europe/Amsterdam",
  );
  await page.getByRole("button", { name: "Refresh diagnostics" }).click();
  await page.goto("/others/publishing/calendar");
  await page.getByRole("button", { name: "Next month" }).click();
  await page.getByRole("button", { name: "Previous month" }).click();
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Posts on/ })).toBeVisible();
  await page.goto("/leads?tab=lists");
  await page
    .getByRole("button", { name: "Create list", exact: true })
    .first()
    .click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("List name").fill("Review group " + tag);
  await dialog
    .getByRole("button", { name: "Create list", exact: true })
    .click();
  await expect(
    page.getByText("Review group " + tag, { exact: true }),
  ).toBeVisible();
  await page.goto("/leads");
  await page
    .getByRole("button", { name: "Add lead", exact: true })
    .first()
    .click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("First name").fill("Jamie");
  await dialog.getByLabel("Last name").fill(tag);
  await dialog.getByRole("button", { name: "Add lead", exact: true }).click();
  await expect(page.getByText("Jamie " + tag, { exact: true })).toBeVisible();
  await page.goto("/templates");
  await page
    .getByRole("button", { name: "New template", exact: true })
    .first()
    .click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Template name").fill("Manual follow-up " + tag);
  await dialog
    .locator("textarea")
    .fill("Thanks for our conversation yesterday.");
  await dialog
    .getByRole("button", { name: "Create template", exact: true })
    .click();
  await expect(
    page.getByText("Manual follow-up " + tag, { exact: true }),
  ).toBeVisible();
  await page.getByRole("complementary", { name: "Sidebar" }).getByRole("button", { name: /account menu/i }).click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
});
