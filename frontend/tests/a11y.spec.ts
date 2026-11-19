import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { account, attempt, callsTo, mockApi, newApi } from "./mock-api";
import { states } from "./states";

/* Automated accessibility checks (axe) on every page and dialog state: no serious or critical violations. */

const WIDTHS = [1280, 360];
const THEMES = ["light", "dark"] as const;

test.describe("axe: no serious or critical violations", () => {
  test.setTimeout(180_000);

  for (const state of states) {
    test(state.name, async ({ page }) => {
      for (const theme of THEMES) for (const width of WIDTHS) {
        if (state.maxWidth && width > state.maxWidth) continue;
        await page.emulateMedia({ colorScheme: theme });
        await page.unrouteAll({ behavior: "ignoreErrors" });
        await page.setViewportSize({ width, height: 900 });
        await mockApi(page, state.api());
        await page.goto(state.path);
        await expect(page.locator("main, [role=dialog]").first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        if (state.prepare) await state.prepare(page);
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page }).analyze();
        const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(
          blocking.map((v) => `${v.id} (${v.impact}) at ${width}px ${theme}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`),
          `${state.name} at ${width}px, ${theme}`,
        ).toEqual([]);
      }
    });
  }
});

test.describe("dialog behaviour", () => {
  test.setTimeout(60_000);

  test("focus stays inside the connect dialog, forwards and backwards, and returns on close", async ({ page }) => {
    await mockApi(page, newApi());
    await page.goto("/linkedin-accounts?view=cards");
    const opener = page.getByRole("button", { name: "Connect LinkedIn account" });
    await opener.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Email or phone")).toBeFocused();
    const insideDialog = () => page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"));
    for (let press = 0; press < 14; press++) {
      await page.keyboard.press("Tab");
      expect(await insideDialog(), `after Tab ${press + 1}`).toBe(true);
    }
    for (let press = 0; press < 14; press++) {
      await page.keyboard.press("Shift+Tab");
      expect(await insideDialog(), `after Shift+Tab ${press + 1}`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();
  });

  test("focus stays inside the edit dialog and the disconnect confirmation", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
    await page.goto("/linkedin-accounts?view=cards");
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const insideDialog = () => page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"));
    for (let press = 0; press < 20; press++) {
      await page.keyboard.press("Tab");
      expect(await insideDialog(), `edit: Tab ${press + 1}`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
    await page.getByRole("menuitem", { name: "Disconnect" }).click();
    for (let press = 0; press < 8; press++) {
      await page.keyboard.press("Tab");
      expect(await insideDialog(), `confirm: Tab ${press + 1}`).toBe(true);
    }
  });

  test("leaving the page mid-attempt stops polling and cancels the attempt", async ({ page }) => {
    const api = newApi({ script: [attempt("starting"), attempt("awaiting_app_approval")] });
    await mockApi(page, api);
    await page.goto("/dashboard");
    await page.getByRole("link", { name: "Sender accounts", exact: true }).first().click();
    await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
    await page.getByLabel("Email or phone").fill("ada@example.com");
    await page.getByLabel("LinkedIn password").fill("Sup3r-Secret-Pw");
    await page.getByRole("dialog").getByRole("button", { name: "Connect LinkedIn account" }).click();
    await expect(page.getByRole("heading", { name: "Approve the sign-in in your LinkedIn app" })).toBeVisible({ timeout: 15_000 });

    await page.goBack(); // a client-side navigation: the dialog and its polling unmount
    await expect(page.getByRole("heading", { name: /^Good (morning|afternoon|evening)/, level: 1 })).toBeVisible();
    await expect.poll(() => callsTo(api, "DELETE", /\/connect\/a1$/).length).toBe(1);
    const polls = callsTo(api, "GET", /\/connect\/a1$/).length;
    await page.waitForTimeout(5000); // two and a half polling intervals
    expect(callsTo(api, "GET", /\/connect\/a1$/)).toHaveLength(polls);
  });
});

test.describe("dropdown menus (not modal)", () => {
  for (const theme of THEMES) {
    test(`Escape closes and returns focus to the trigger; an outside click closes (${theme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
      await page.goto("/linkedin-accounts?view=cards");
      const trigger = page.getByRole("button", { name: "More actions for Ada Lovelace" });

      await trigger.focus();
      await page.keyboard.press("Enter");  // opened from the keyboard, the first item takes focus (a pointer open focuses the menu itself)
      const menu = page.getByRole("menu");
      await expect(menu).toBeVisible();
      await expect(menu.getByRole("menuitem").first()).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
      await expect(trigger).toBeFocused();

      await trigger.click();
      await expect(menu).toBeVisible();
      await page.getByRole("heading", { name: "Sender accounts", level: 1 }).click();
      await expect(menu).toBeHidden();

      // The account menu in the shell behaves the same way.
      const userMenu = page.getByRole("button", { name: /account menu/i }).last();
      await userMenu.click();
      await expect(page.getByRole("menu")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu")).toBeHidden();
      await expect(userMenu).toBeFocused();
    });
  }
});
