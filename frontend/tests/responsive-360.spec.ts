import { test, expect } from "@playwright/test";
import { mockApi } from "./mock-api";
import { states } from "./states";

/* At 360px every page and dialog state fits the screen: no sideways scroll, nothing pushed past the edge. */

test.describe("360px", () => {
  test.setTimeout(60_000);

  for (const state of states) {
    test(state.name, async ({ page }) => {
      await page.setViewportSize({ width: 360, height: 740 });
      await mockApi(page, state.api());
      await page.goto(state.path);
      await expect(page.locator("main, [role=dialog]").first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      if (state.prepare) await state.prepare(page);
      await page.waitForTimeout(300);
      const overflow = await page.evaluate(() => {
        const width = window.innerWidth;
        const past = [...document.querySelectorAll("body *")].filter((el) => {
          const box = el.getBoundingClientRect();
          const clipped = el.closest("[class*=overflow-x-auto], [class*=overflow-auto], [class*=overflow-hidden], datalist, [aria-hidden=true]");
          return !clipped && box.width > 0 && box.right > width + 1;
        });
        return { scroll: document.documentElement.scrollWidth, width, past: past.slice(0, 5).map((el) => `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)}`) };
      });
      expect(overflow.scroll, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width);
      expect(overflow.past, JSON.stringify(overflow)).toEqual([]);
    });
  }
});
