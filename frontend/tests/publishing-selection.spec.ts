import { test, expect, type Locator, type Page } from "@playwright/test";
import fs from "node:fs";
import { account, mockApi, newApi, post, publishingAccount } from "./mock-api";

/* The publishing calendar's selected day and the studio's selected row are styled by plain CSS classes
   (selected-day, selected-row) that a CSS clean-up once deleted. Hold both to a visible difference and keep
   a screenshot of each for review. */

const DIR = "test-results/review/selection";
const background = (locator: Locator) => locator.evaluate((el) => getComputedStyle(el).backgroundColor);
const surfaceMuted = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.background = "rgb(var(--surface-muted))";
    document.body.append(probe);
    const value = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return value;
  });

test.beforeAll(() => fs.mkdirSync(DIR, { recursive: true }));

for (const theme of ["light", "dark"] as const) {
  test(`the calendar marks the selected day (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    const posts = [post("p-a", "Hiring lessons", { status: "scheduled", scheduledAt: "2026-11-20T09:00:00Z" })];
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")], publishing: { accounts: [publishingAccount()], posts, activity: [] } }));
    await page.clock.setFixedTime(new Date("2026-11-15T12:00:00Z"));
    await page.goto("/others/publishing/calendar");

    const day = page.getByRole("button", { name: /^20.*Hiring lessons.*2026-11-20: 1 post$/ });
    const other = page.getByRole("button", { name: /^21.*2026-11-21: 0 posts$/ });
    await expect(day).toBeVisible();
    const before = await background(day);
    await day.click();
    await page.mouse.move(0, 0); // the hover style matches the selected style; take the pointer away
    await expect(page.getByRole("heading", { name: "Posts on 2026-11-20" })).toBeVisible();
    await expect(day).toHaveClass(/\bselected-day\b/);
    await expect.poll(() => background(day)).toBe(await surfaceMuted(page));
    expect(await background(day)).not.toBe(before);
    expect(await background(day)).not.toBe(await background(other));
    // The scheduled post inside the day keeps its tint (state-scheduled).
    const chip = day.locator(".calendar-post.state-scheduled");
    expect(await background(chip)).not.toBe("rgba(0, 0, 0, 0)");
    await page.screenshot({ path: `${DIR}/calendar-selected-day-${theme}.png`, fullPage: true });
  });

  test(`the studio marks the selected post row (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    const posts = [post("p-a", "Hiring lessons"), post("p-b", "Quarter in review")];
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")], publishing: { accounts: [publishingAccount()], posts, activity: [] } }));
    await page.goto("/others/publishing/studio?id=p-b");

    const selected = page.locator(".post-row", { hasText: "Quarter in review" });
    const other = page.locator(".post-row", { hasText: "Hiring lessons" });
    await expect(selected).toHaveClass(/\bselected-row\b/);
    await expect(other).not.toHaveClass(/\bselected-row\b/);
    await page.mouse.move(0, 0);
    await expect.poll(() => background(selected)).toBe(await surfaceMuted(page));
    expect(await background(selected)).not.toBe(await background(other));
    await page.screenshot({ path: `${DIR}/studio-selected-row-${theme}.png`, fullPage: true });
  });
}
