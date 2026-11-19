import { test, expect, type Page } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* The lead lists page: search, filter, sort, export one list, delete with a confirmation, and its empty and error states. The API is mocked. */

const list = (id: string, name: string, leadCount: number, over: Record<string, unknown> = {}) => ({ id, name, leadCount, description: null, color: "primary", createdAt: "2026-11-01T00:00:00Z", ...over });
const LISTS = [list("L1", "Spring prospects", 12, { description: "Founders" }), list("L2", "Empty list", 0), list("L3", "Conference", 40)];

const open = async (page: Page, lists = LISTS) => {
  const api = newApi({ lists: lists as never, builderEmpty: lists.length === 0 });
  await mockApi(page, api);
  await page.goto("/leads?tab=lists");
  await page.waitForLoadState("networkidle");
  return api;
};

const names = (page: Page) => page.getByRole("heading", { level: 3 }).allTextContents();

test("lists can be searched, filtered by size and sorted, with a count that says how many are shown", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("status").filter({ hasText: "of 3 lists" })).toHaveText("3 of 3 lists");
  await page.getByLabel("Search lists").fill("found");
  expect(await names(page)).toEqual(["Spring prospects"]); // the description is searched too
  await expect(page.getByRole("status").filter({ hasText: "of 3 lists" })).toHaveText("1 of 3 lists");
  await page.getByLabel("Search lists").fill("zzz");
  await expect(page.getByText("No list matches.")).toBeVisible();
  await page.getByLabel("Search lists").fill("");
  await page.getByLabel("Show").selectOption("empty");
  expect(await names(page)).toEqual(["Empty list"]);
  await page.getByLabel("Show").selectOption("with");
  await page.getByLabel("Sort by").selectOption("size");
  expect(await names(page)).toEqual(["Conference", "Spring prospects"]);
  await page.getByLabel("Sort by").selectOption("name");
  expect(await names(page)).toEqual(["Conference", "Spring prospects"]);
});

test("a list exports as a CSV file and opens its leads", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Actions for Spring prospects" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("synex-list-Spring-prospects.csv");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await page.getByRole("button", { name: "Actions for Conference" }).click();
  await page.getByRole("menuitem", { name: "View leads" }).click();
  await expect(page).toHaveURL(/\/leads\?listId=L3/);
});

test("deleting a list asks first, says the leads stay, and removes only that list", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Actions for Empty list" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Leads in this list won't be deleted");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  const deletes = () => callsTo(api, "POST", /^\/lead-lists$/).filter((c) => (c.body as { action?: string })?.action === "delete");
  expect(deletes()).toHaveLength(0);
  await page.getByRole("button", { name: "Actions for Empty list" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("heading", { level: 3, name: "Empty list" })).toHaveCount(0);
  expect(deletes().map((c) => (c.body as { id: string }).id)).toEqual(["L2"]);
});

test("no lists shows the empty state, and a failed load shows a retry", async ({ page }) => {
  await open(page, []);
  await expect(page.getByText("No lead lists yet")).toBeVisible();
  const failing = newApi();
  await mockApi(page, failing);
  await page.route("**/lead-lists", (route) => route.fulfill({ status: 500, headers: { "access-control-allow-origin": "*", "content-type": "application/json" }, body: JSON.stringify({ detail: "boom" }) }));
  await page.goto("/leads?tab=lists");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("keyboard: the search, filters and a list's menu are reachable and work without a mouse", async ({ page }) => {
  await open(page);
  await page.getByLabel("Search lists").focus();
  await page.keyboard.type("conf");
  expect(await names(page)).toEqual(["Conference"]);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Show")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Sort by")).toBeFocused();
  const menu = page.getByRole("button", { name: "Actions for Conference" });
  await menu.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Export CSV" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
});
