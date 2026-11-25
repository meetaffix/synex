import { test, expect } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";
import { API_PORT } from "./support";

/* The "How would you like to add leads?" dialog. The API is mocked; nothing is read from LinkedIn. */

const source = (page: import("@playwright/test").Page, text: RegExp | string) => page.getByRole("list", { name: "Lead sources" }).locator("button").filter({ hasText: text });

const open = async (page: import("@playwright/test").Page) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")] });
  await mockApi(page, api);
  await page.goto("/leads");
  await page.getByRole("button", { name: /^Add leads?$/ }).first().click();
  return api;
};

test("every source is listed; the unbuilt one says Coming soon and cannot be chosen", async ({ page }) => {
  await open(page);
  const list = page.getByRole("list", { name: "Lead sources" });
  await expect(list.locator("button")).toHaveCount(9);
  await expect(source(page, /LinkedIn group members/)).toBeDisabled();
  await expect(list.getByText(/Coming soon: LinkedIn only shows/)).toBeVisible();
  await expect(list.getByText("Needs a Sales Navigator subscription on the sender account.")).toBeVisible();
});

test("an event: the hint warns about attending, the estimate shows before anything runs, and a wrong address is explained", async ({ page }) => {
  const api = await open(page);
  await source(page, /LinkedIn event attendees/).click();
  await expect(page.getByText(/must be marked as attending the event/).first()).toBeVisible();
  await expect(page.getByTestId("estimate")).toContainText("up to 50 people, about 15 page loads, around 5 minutes");
  await expect(page.getByTestId("estimate")).toContainText("at most 15 pages; run it again for more");
  await page.getByLabel("Links or data").fill("https://example.com/bad");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("alert")).toHaveText("Paste a LinkedIn event address (it contains linkedin.com/events/).");
  await page.getByLabel("Links or data").fill("https://www.linkedin.com/events/world-summit-123/");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("list", { name: "First people found" })).toContainText("Katherine Johnson", { timeout: 15000 });
  expect(callsTo(api, "POST", /\/lead-collections$/).length).toBe(2);
});

test("company sources say they make a list of companies and hide the people-only options", async ({ page }) => {
  await open(page);
  await source(page, /LinkedIn companies/).click();
  await expect(page.getByText(/makes a list of companies, not people/)).toBeVisible();
  await expect(page.getByText("People already contacted")).toHaveCount(0);
  await expect(page.getByLabel("Links or data")).toBeVisible();
});

test("a pasted-links source needs no sender and says nothing is read from LinkedIn", async ({ page }) => {
  await open(page);
  await expect(source(page, /Paste profile links/)).toContainText("Nothing is read from LinkedIn");
  await source(page, /Paste profile links/).click();
  await expect(page.getByLabel("Sender account (reads LinkedIn)")).toHaveCount(0);
  await expect(page.getByTestId("estimate")).toHaveCount(0);
});

test("the estimate says how many page reads the chosen account has left today", async ({ page }) => {
  await open(page);
  await source(page, /LinkedIn event attendees/).click();
  await expect(page.getByTestId("estimate")).toContainText("This account can read 12 more pages today.");
});

test("a CSV source offers a sample file and refuses a file over 5 MB with the fix", async ({ page }) => {
  await open(page);
  await source(page, /CSV or Google Sheets/).click();
  await expect(page.getByRole("link", { name: "Download a sample CSV" })).toHaveAttribute("download", "synex-sample-leads.csv");
  await page.getByLabel("CSV file").setInputFiles({ name: "big.csv", mimeType: "text/csv", buffer: Buffer.alloc(5_100_000, "a") });
  await expect(page.getByRole("alert")).toHaveText("That file is larger than 5 MB. Split it into smaller files.");
});

/* My connections is read by the outreach worker. The page must say when no worker is running, and a request still being read when the
   window is closed must still finish: the old page stopped watching and the finished list never reached the campaign. */
const connectionsRoutes = async (page: import("@playwright/test").Page, states: Array<Record<string, unknown>>) => {
  const base = { id: "c1", source: "connections", label: "My connections", listName: "My connections", limit: 30000, options: {}, fetched: 0, created: 0, skipped: {},
    detail: null, listId: null, accountId: "a1", estimate: { people: 0, pages: 0, minutes: 0, reads_linkedin: true }, createdAt: "2026-11-20T10:00:00Z", preview: null };
  let reads = 0;
  await page.route((url) => url.port === API_PORT && url.pathname.startsWith("/lead-collections"), async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const cors = { "access-control-allow-origin": request.headers()["origin"] ?? "*", "access-control-allow-credentials": "true", "access-control-allow-headers": "content-type" };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { ...cors, "access-control-allow-methods": "GET,POST,OPTIONS" } });
    const send = (body: unknown) => route.fulfill({ status: 200, headers: cors, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/lead-collections/sources") return send([{ id: "connections", label: "My connections", readsLinkedin: true, available: true, note: null, maxLeads: 30000, produces: "people" }]);
    if (path === "/lead-collections/estimate") return send({ people: 0, pages: 0, minutes: 0, reads_linkedin: true, maxPagesPerRun: 15, pagesLeftToday: null });
    if (request.method() === "POST") return send({ ...base, ...states[0] });
    return send({ ...base, ...states[Math.min(reads++, states.length - 1)] });
  });
};

const openConnections = async (page: import("@playwright/test").Page, states: Array<Record<string, unknown>>, extra?: () => Promise<void>) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await connectionsRoutes(page, states);
  if (extra) await extra();
  await page.goto("/leads");
  await page.getByRole("button", { name: /^Add leads?$/ }).first().click();
};

test("My connections with no worker running says so, and how to start it", async ({ page }) => {
  await openConnections(page, [{ status: "queued", workerActive: false }]);
  await source(page, /My connections/).click();
  await page.getByRole("button", { name: "Add all my connections" }).click();
  await expect(page.getByText("No worker is running, so this cannot start yet")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Synex is not reading LinkedIn right now");
});

test("My connections: closing the window while it is read still tells you when the leads are added", async ({ page }) => {
  await openConnections(page, [{ status: "queued", workerActive: true }, { status: "queued", workerActive: true }, { status: "completed", created: 3, listId: "l9" }]);
  await source(page, /My connections/).click();
  await page.getByRole("button", { name: "Add all my connections" }).click();
  await expect(page.getByText("Starting…")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("3 leads added to My connections.")).toBeVisible({ timeout: 15_000 });
});

test("My connections: one failed check does not end the watch", async ({ page }) => {
  let failed = false;
  await openConnections(page, [{ status: "queued", workerActive: true }, { status: "completed", created: 3, listId: "l9" }], async () => {
    await page.route((url) => url.port === API_PORT && url.pathname === "/lead-collections/c1", (route) => {
      if (route.request().method() === "GET" && !failed) { failed = true; return route.abort(); }
      return route.fallback();
    });
  });
  await source(page, /My connections/).click();
  await page.getByRole("button", { name: "Add all my connections" }).click();
  await expect(page.getByText(/Done: 3 new leads added/)).toBeVisible({ timeout: 20_000 });
});
