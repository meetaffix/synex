import { test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { mockApi } from "./mock-api";
import { states } from "./states";

/* Opt-in: SCREENS=area-3 SCREEN_FILTER=account- npx playwright test screens.spec.ts (SCREEN_THEMES=light SCREEN_WIDTHS=1280 for a quick look)
   Saves each screen in both themes at 360, 768 and 1280 under docs/reports/screens/<area>/ so they can be looked at. */

const area = process.env.SCREENS;
const filter = process.env.SCREEN_FILTER ?? "";
const themes = (process.env.SCREEN_THEMES ?? "light,dark").split(",") as ("light" | "dark")[];
const widths = (process.env.SCREEN_WIDTHS ?? "360,768,1280").split(",").map(Number);

test.describe("screens", () => {
  test.skip(!area, "set SCREENS=<area> to capture");
  test.setTimeout(300_000);
  for (const state of states.filter((s) => s.name.startsWith(filter))) {
    test(state.name, async ({ page }) => {
      const dir = `../docs/reports/screens/${area}`;
      mkdirSync(dir, { recursive: true });
      for (const theme of themes) for (const width of widths) {
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
