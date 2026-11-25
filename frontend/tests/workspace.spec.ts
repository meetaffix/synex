import { test, expect } from "@playwright/test";
import fs from "node:fs";
test("publishing journey, all routes, and responsive layouts", async ({
  page,
}) => {
  test.setTimeout(120_000); // Includes 42 full-page screenshots across three viewport sizes.
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-Test-Password!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)/, level: 1 }),
  ).toBeVisible();
  await page.goto("/others/publishing");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Create post", exact: true }).click();
  await page
    .getByLabel("Internal title")
    .fill("A thoughtful publishing workflow");
  await page
    .getByLabel("Post", { exact: true })
    .fill(
      "Good publishing starts with a clear idea.\n\nWrite with care. Review the details. Share when the time is right.",
    );
  await page
    .getByLabel("Publish as")
    .selectOption({ label: "Alex Morgan · Test account · Connected" });
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Internal title")).toHaveValue(
    "A thoughtful publishing workflow",
  );
  await page.getByRole("button", { name: "Schedule", exact: true }).click();
  await page.getByLabel("Date and time").fill("2099-11-04T10:30");
  await page.getByLabel("Time zone", { exact: true }).fill("Europe/Amsterdam");
  await page.getByRole("button", { name: "Approve & schedule" }).click();
  await expect(
    page.getByRole("button", { name: "Pause & edit" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause & edit" }).click();
  await expect(
    page.getByRole("button", { name: "Publish now", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Publish now", exact: true }).click();
  await page.getByRole("button", { name: "Approve & publish" }).click();
  const executed = await page.request.post(
    "http://127.0.0.1:8011/test/execute",
    { headers: { Origin: "http://127.0.0.1:5174" } },
  );
  expect(executed.ok()).toBeTruthy();
  expect((await executed.json()).mockedRequests).toBe(1);
  await page.reload();
  await expect(
    page.getByRole("link", { name: "View published post" }),
  ).toBeVisible();
  await page.goto("/others/publishing/studio?new=2");
  await page.getByLabel("Internal title").fill("Notes for next week");
  await page
    .getByLabel("Post", { exact: true })
    .fill("A second draft to review with the team.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
  fs.mkdirSync("test-results/screenshots", { recursive: true });
  const routes = [
    "dashboard",
    "inbox",
    "campaigns",
    "linkedin-accounts",
    "leads",
    "templates",
    "others",
    "others/publishing",
    "others/publishing/studio",
    "others/publishing/calendar",
    "others/publishing/queue",
    "others/publishing/activity",
    "others/publishing/analytics",
    "others/publishing/connections",
    "settings",
    "help",
  ];
  for (const width of [1440, 834, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of routes) {
      await page.goto("/" + route);
      await expect(page.locator("h1").first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready.then(() => true));
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
        `${route} overflow at ${width}`,
      ).toBeTruthy();
      await page.screenshot({
        path: `test-results/screenshots/${route}-${width}.png`,
        fullPage: true,
      });
    }
  }
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("link", { name: "Campaigns", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Campaigns", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(errors).toEqual([]);
});
