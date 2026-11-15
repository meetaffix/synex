import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { mockApi } from "./mock-api";
import { states } from "./states";

/* Captures every page and dialog state at 360, 768 and 1280 px, in light and dark, into
   test-results/review/<theme>/ for visual inspection. The theme follows the emulated device setting,
   which is the app's default ("Match my device"). */

const WIDTHS = [360, 768, 1280];
const THEMES = ["light", "dark"] as const;

test.describe("review screenshots", () => {
  test.setTimeout(180_000);

  for (const state of states) {
    test(state.name, async ({ page }) => {
      for (const theme of THEMES) {
        const dir = `test-results/review/${theme}`;
        fs.mkdirSync(dir, { recursive: true });
        // Reduced motion: nothing is mid-transition when the page is captured (a full-page capture resizes the viewport).
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        for (const width of WIDTHS) {
          if (state.maxWidth && width > state.maxWidth) continue;
          await page.unrouteAll({ behavior: "ignoreErrors" });
          await page.setViewportSize({ width, height: 900 });
          await mockApi(page, state.api());
          await page.goto(state.path);
          await expect(page.locator("main, [role=dialog], .auth-shell").first()).toBeVisible();
          await page.waitForLoadState("networkidle");
          if (state.prepare) await state.prepare(page);
          await page.waitForTimeout(400);
          await page.screenshot({ path: `${dir}/${state.name}-${width}.png`, fullPage: true });
        }
      }
    });
  }
});
