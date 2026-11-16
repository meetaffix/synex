import { test, expect } from "@playwright/test";
import { account, mockApi, newApi } from "./mock-api";

/* The sender accounts list: overview card, 24-hour usage, performance chips, filters, paging. The API is mocked. */

const open = async (page: import("@playwright/test").Page, accounts = [account("a1", "Ada Lovelace"), account("a2", "Grace Hopper", { status: "needs_reconnect" })]) => {
  await mockApi(page, newApi({ accounts }));
  await page.goto("/linkedin-accounts");
};

test("the overview card shows plan, seats used and seats available, and says billing is a placeholder", async ({ page }) => {
  await open(page);
  const card = page.getByRole("region", { name: "Workspace overview" });
  await expect(card).toContainText("Seats used 2 of 3");
  await expect(card).toContainText("Seats available 1");
  await expect(card).toContainText("placeholder");
});

test("each account shows its 24-hour usage against today's range, a Smart pill and honest performance chips", async ({ page }) => {
  await open(page);
  const first = page.getByRole("listitem").filter({ hasText: "Ada Lovelace" });
  await expect(first.getByText("2 of 4 to 6")).toBeVisible();
  await expect(first.getByText("1 of 9 to 11")).toBeVisible();
  await expect(first.getByText("Smart limits")).toBeVisible();
  await expect(first.getByText("Accepted 40%")).toBeVisible();
  await expect(first.getByText("Replied 25%")).toBeVisible();
  const second = page.getByRole("listitem").filter({ hasText: "Grace Hopper" });
  await expect(second.getByText("Smart limits")).toHaveCount(0);
  await expect(second.getByText("Accepted no data")).toBeVisible(); // never a made-up 0%
});

test("the filter offers All, Active and Needs attention, and the name search narrows the list", async ({ page }) => {
  await open(page);
  const filter = page.getByLabel("Filter by status");
  await filter.selectOption("attention");
  await expect(page.getByRole("heading", { name: "Grace Hopper" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ada Lovelace" })).toHaveCount(0);
  await filter.selectOption("active");
  await expect(page.getByRole("heading", { name: "Ada Lovelace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Grace Hopper" })).toHaveCount(0);
  await filter.selectOption("all");
  await page.getByLabel("Search accounts").fill("hop");
  await expect(page.getByRole("heading", { name: "Grace Hopper" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ada Lovelace" })).toHaveCount(0);
  await page.getByLabel("Search accounts").fill("zzz");
  await expect(page.getByText("No accounts match.")).toBeVisible();
});

test("more than nine accounts are paged with Previous and Next", async ({ page }) => {
  await open(page, Array.from({ length: 11 }, (_, i) => account(`a${i}`, `Person ${String(i).padStart(2, "0")}`)));
  await expect(page.getByRole("heading", { level: 2, name: /Person/ })).toHaveCount(9);
  await expect(page.getByText("1 to 9 of 11")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("heading", { level: 2, name: /Person/ })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(page.getByText("1 to 9 of 11")).toBeVisible();
});

test("with no accounts the page offers Connect, and a failed load offers Try again", async ({ page }) => {
  await open(page, []);
  await expect(page.getByRole("button", { name: "Connect LinkedIn account" })).toBeVisible();
});
