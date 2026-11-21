import { test, expect } from "@playwright/test";
import { account, mockApi, newApi } from "./mock-api";
import { API_PORT } from "./support";

/* A long import (your connections) keeps running in the background: a card on every page shows the live count, and the person can go anywhere. */

const running = (fetched: number, status = "running") => [{
  id: "c9", source: "connections", label: "My connections", status, listName: "My connections", limit: 30000, fetched, created: 0, detail: null, listId: null,
  estimate: { people: 30000 }, options: {}, skipped: {}, preview: null, accountId: "a1", createdAt: "2026-11-21T10:00:00Z",
}];

test("an import in progress shows its live count on every page, and Stop ends it", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
  await mockApi(page, api);
  let rows = running(124);
  let stopped = false;
  await page.route((url) => url.port === String(API_PORT) && url.pathname === "/lead-collections", (route) => route.fulfill({ json: rows }));
  await page.route((url) => url.port === String(API_PORT) && url.pathname === "/lead-collections/c9/stop", (route) => { stopped = true; rows = running(124, "stopped"); return route.fulfill({ json: rows[0] }); });
  await page.goto("/templates");
  const card = page.getByRole("complementary", { name: "Imports in progress" });
  await expect(card).toContainText("Importing your connections");
  await expect(card).toContainText("124");
  await page.getByRole("link", { name: "Inbox" }).first().click(); // free to go anywhere
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Stop" }).click();
  await expect.poll(() => stopped).toBe(true);
  await expect(card).toBeHidden();
});

test("nothing running shows no card", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.route((url) => url.port === String(API_PORT) && url.pathname === "/lead-collections", (route) => route.fulfill({ json: [] }));
  await page.goto("/templates");
  await expect(page.getByRole("heading", { name: "Templates", level: 1 })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Imports in progress" })).toHaveCount(0);
});
