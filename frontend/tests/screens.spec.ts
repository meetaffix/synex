import { test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { mockApi } from "./mock-api";
import { states } from "./states";

/* Opt-in: SCREENS=area-3 SCREEN_FILTER=account- npx playwright test screens.spec.ts
   Saves each screen in both themes at 360, 768 and 1280 under docs/reports/screens/<area>/ so they can be looked at. */

const area = process.env.SCREENS;
const filter = process.env.SCREEN_FILTER ?? "";

test.describe("screens", () => {
  test.skip(!area, "set SCREENS=<area> to capture");
  test.setTimeout(300_000);
  for (const state of states.filter((s) => s.name.startsWith(filter))) {
    test(state.name, async ({ page }) => {
      const dir = `../docs/reports/screens/${area}`;
      mkdirSync(dir, { recursive: true });
      for (const theme of ["light", "dark"] as const) for (const width of [360, 768, 1280]) {
        await page.emulateMedia({ colorScheme: theme });
        await page.unrouteAll({ behavior: "ignoreErrors" });
        await page.setViewportSize({ width, height: 900 });
        await mockApi(page, state.api());
        await page.goto(state.path);
        await page.locator("main, [role=dialog]").first().waitFor();
        await page.waitForLoadState("networkidle");
        if (state.prepare) await state.prepare(page);
        await page.waitForTimeout(400);
        await page.screenshot({ path: `${dir}/${state.name}-${theme}-${width}.png`, fullPage: true });
      }
    });
  }
});
