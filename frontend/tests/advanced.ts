import type { Page } from "@playwright/test";

/** Settings fold technical options into "Advanced" sections. Tests that use them open every fold once the page has loaded. */
export async function openAdvanced(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.locator("details").evaluateAll((folds) => folds.forEach((fold) => { (fold as HTMLDetailsElement).open = true; }));
}
