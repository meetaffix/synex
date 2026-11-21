import { test, expect } from "@playwright/test";
import { account, mockApi, newApi } from "./mock-api";
import { API_PORT } from "./support";

const api = (path: string) => (url: URL) => url.port === API_PORT && url.pathname === path;

/* The account menu in the sidebar opens Account settings, the settings page shows the plan, and the audit log page can be deleted only by typing DELETE. The API is mocked. */

test("Account settings in the account menu opens the settings page", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /account menu/i }).first().click();
  await page.getByRole("menuitem", { name: "Account settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
});

test("the settings page shows the plan from the server, and changing plan says it is not available", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.route(api("/plan"), (route) => route.fulfill({ json: { plan: "free", name: "Demo", limits: { assistantMinutes: 60 }, seats: { used: 1, limit: 1 }, assistantMinutes: { used: 12, limit: 60, month: "2026-11" },
    plans: [{ id: "free", name: "Demo", assistantMinutes: 60, seats: 1, dailyInvites: 10, dailyMessages: 20, dailyVisits: 20, current: true }, { id: "pro", name: "Pro", assistantMinutes: 600, seats: 15, dailyInvites: 30, dailyMessages: 80, dailyVisits: 60, current: false }], canManage: true, upgradeAvailable: false, upgradeNote: "Changing plan is not available yet: billing is not built." } }));
  await page.goto("/settings");
  await expect(page.getByText("Plan: Demo")).toBeVisible();
  await expect(page.getByTestId("plan-seats")).toContainText("1 of 1 in use");
  await expect(page.getByTestId("plan-usage")).toContainText("12 of 60 used in 2026-11");
  await expect(page.getByRole("button", { name: /Change plan/ })).toBeDisabled();
});

test("the audit log can be deleted only by typing DELETE, and an admin sees the button", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  let deleted: unknown = null;
  await page.route(api("/audit"), (route) => {
    if (route.request().method() === "DELETE") { deleted = route.request().postDataJSON(); return route.fulfill({ json: { removed: 2, remaining: 1 } }); }
    return route.fulfill({ json: { items: [{ id: "1", at: "2026-11-20T09:00:00Z", source: "linkedin", who: "Meet Affix", action: "send_invite", status: "ok", detail: "Done." }, { id: "2", at: "2026-11-20T08:00:00Z", source: "assistant", who: "Affix", action: "create_template", status: "applied", detail: "" }], total: 2, limit: 25, offset: 0, canDelete: true } });
  });
  await page.goto("/settings/audit");
  await expect(page.getByRole("table")).toContainText("Meet Affix");
  await page.getByRole("button", { name: "Delete audit log" }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: "Delete audit log" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Type DELETE to confirm").fill("delete");
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await confirm.click();
  await expect.poll(() => deleted).toEqual({ confirm: "DELETE" });
});

test("a member who cannot delete sees no delete button", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.route(api("/audit"), (route) => route.fulfill({ json: { items: [], total: 0, limit: 25, offset: 0, canDelete: false } }));
  await page.goto("/settings/audit");
  await expect(page.getByText("Nothing here yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete audit log" })).toHaveCount(0);
});

test("the audit log pages through its entries and filters by source", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  const rows = Array.from({ length: 31 }, (_, i) => ({ id: `r${i}`, at: `2026-11-16T10:${String(i).padStart(2, "0")}:00Z`, source: i === 30 ? "settings" : "linkedin", who: i === 30 ? "Affix" : "Meet Affix", action: "send_invite", status: i === 3 ? "failed" : "ok", detail: `Entry ${i}` }));
  await page.route(api("/audit"), (route) => {
    const q = new URL(route.request().url()).searchParams;
    const mine = rows.filter((r) => (q.get("source") ?? "all") === "all" || r.source === q.get("source"));
    const offset = Number(q.get("offset") ?? 0), limit = Number(q.get("limit") ?? 25);
    return route.fulfill({ json: { items: mine.slice(offset, offset + limit), total: mine.length, limit, offset, canDelete: false } });
  });
  await page.goto("/settings/audit");
  await page.getByLabel("Show").selectOption("all"); // the page opens on messages and invitations; this checks the whole log
  await expect(page.getByRole("status").filter({ hasText: "of 31" })).toHaveText("1 to 25 of 31");
  await expect(page.getByRole("button", { name: "Newer" })).toBeDisabled();
  await page.getByRole("button", { name: "Older" }).click();
  await expect(page.getByRole("status").filter({ hasText: "of 31" })).toHaveText("26 to 31 of 31");
  await page.getByLabel("Show").selectOption("settings");
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(2);
  await expect(page.getByRole("table")).toContainText("Affix");
});
