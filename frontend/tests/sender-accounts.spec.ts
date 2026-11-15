import { test, expect, type Page } from "@playwright/test";
import { API_PORT } from "./support";

/* The API is mocked at the network layer; no backend or LinkedIn is involved. */

interface Call {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
}
interface AttemptShape {
  attemptId: string;
  state: string;
  challenge?: { type: string; hint?: string };
  error?: { code: string; message: string };
  accountId?: string;
}
interface Api {
  accounts: Record<string, unknown>[];
  /** Served one per poll; the last one repeats. */
  script: AttemptShape[];
  calls: Call[];
  onCode: (code: string, api: Api) => void;
  proxyTest: (body: Record<string, unknown>) => Record<string, unknown>;
  linkInfo: { status: number; body: Record<string, unknown> };
  listStatus: number;
}

const USER = { id: "u1", email: "owner@example.com", fullName: "Owner Test", role: "Member", plan: "free", createdAt: "2026-01-01T00:00:00Z" };
const account = (over: Record<string, unknown> = {}) => ({
  id: "acc1",
  name: "Ada Lovelace",
  headline: "Engineer at Analytical Engines",
  profileUrl: "https://www.linkedin.com/in/ada",
  avatarUrl: null,
  status: "connected",
  dailyActionLimit: 50,
  dailyActionsUsed: 12,
  ceilings: { dailyActions: 200, connectionRequestsPerDay: 40, connectionRequestsPerWeek: 150, messagesPerDay: 100, profileVisitsPerDay: 80, followsPerDay: 50 },
  proxyConfigured: false,
  syncMode: "synex_only",
  canChangeSyncMode: true,
  pausedReason: null,
  lastCheckedAt: "2026-11-14T10:00:00Z",
  connectedAt: "2026-11-01T10:00:00Z",
  ...over,
});
const attempt = (state: string, extra: Partial<AttemptShape> = {}): AttemptShape => ({ attemptId: "a1", state, ...extra });

function newApi(over: Partial<Api> = {}): Api {
  return {
    accounts: [],
    script: [attempt("starting")],
    calls: [],
    onCode: () => undefined,
    proxyTest: () => ({ ok: true, latencyMs: 142, exitIp: "203.0.113.7", country: "NL" }),
    linkInfo: { status: 200, body: { accountName: "Ada Lovelace", avatarUrl: null, expiresAt: "2026-11-15T10:00:00Z" } },
    listStatus: 200,
    ...over,
  };
}

async function mockApi(page: Page, api: Api) {
  await page.route(
    (url) => url.port === API_PORT,
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method();
      const cors = {
        "access-control-allow-origin": request.headers()["origin"] ?? "*",
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "content-type",
        "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
      };
      if (method === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      let body: Record<string, unknown> | null = null;
      try {
        body = request.postDataJSON();
      } catch {
        body = null;
      }
      const path = url.pathname;
      api.calls.push({ method, path, body });
      const json = (status: number, data: unknown) =>
        route.fulfill({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(data) });
      const empty = () => route.fulfill({ status: 204, headers: cors });

      if (path === "/auth/me") return json(200, USER);
      if (path === "/linkedin-accounts" && method === "GET")
        return api.listStatus === 200 ? json(200, api.accounts) : json(api.listStatus, { detail: "The server is unavailable." });
      if (path === "/linkedin-accounts/proxy-test") return json(200, api.proxyTest(body ?? {}));
      const reconnectInfo = path.match(/^\/reconnect\/([^/]+)$/);
      if (reconnectInfo && method === "GET") return json(api.linkInfo.status, api.linkInfo.body);

      const flow = path.match(/^\/(?:linkedin-accounts|reconnect\/[^/]+)\/connect(?:\/(a1)(\/code)?)?$/);
      if (flow) {
        if (method === "POST" && !flow[1]) return json(202, attempt("starting"));
        if (method === "DELETE") return empty();
        if (method === "POST" && flow[2]) {
          api.onCode(String(body?.code), api);
          return json(200, attempt("starting"));
        }
        const next = api.script.length > 1 ? api.script.shift() : api.script[0];
        if (next?.state === "succeeded" && !api.accounts.some((a) => a.id === "acc1")) api.accounts.push(account());
        return json(200, next);
      }

      const one = path.match(/^\/linkedin-accounts\/(acc1)(\/check|\/reconnect-link)?$/);
      if (one) {
        const current = api.accounts.find((a) => a.id === "acc1");
        if (one[2] === "/reconnect-link")
          return json(200, { url: "http://localhost:5173/reconnect/tok123", expiresAt: "2026-11-15T10:00:00Z" });
        if (method === "PATCH" && current) {
          if (body && "paused" in body) current.status = body.paused ? "paused" : "connected";
          if (body && "dailyActionLimit" in body) current.dailyActionLimit = body.dailyActionLimit;
          if (body && "syncMode" in body) current.syncMode = body.syncMode;
          return json(200, current);
        }
        if (method === "DELETE" && current) {
          current.status = "disconnected";
          return empty();
        }
        if (current) return json(200, current);
      }
      return json(404, { detail: "Not mocked" });
    },
  );
}

const callsTo = (api: Api, method: string, pattern: RegExp) => api.calls.filter((c) => c.method === method && pattern.test(c.path));

async function openConnect(page: Page, api: Api) {
  await mockApi(page, api);
  await page.goto("/linkedin-accounts");
  await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
}

async function fillCredentials(page: Page, identifier = "ada@example.com") {
  await page.getByLabel("Email or phone").fill(identifier);
  await page.getByLabel("LinkedIn password").fill("Sup3r-Secret-Pw");
}

const submit = (page: Page) => page.getByRole("dialog").getByRole("button", { name: "Connect LinkedIn account" }).click();

test.describe("sender accounts", () => {
  test.setTimeout(60_000);

  test("empty state explains sender accounts and offers one primary action", async ({ page }) => {
    await mockApi(page, newApi());
    await page.goto("/linkedin-accounts");
    await expect(page.getByRole("heading", { name: "Sender accounts", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No sender accounts yet" })).toBeVisible();
    await expect(page.getByText("A sender account is a LinkedIn profile that Synex sends")).toBeVisible();
    await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("the connect dialog opens on the credentials form", async ({ page }) => {
    await openConnect(page, newApi());
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Connect LinkedIn account" })).toBeVisible();
    await expect(page.getByLabel("Email or phone")).toBeFocused();
    await expect(page.getByLabel("LinkedIn password")).toBeVisible();
    await expect(dialog.getByText("Synex uses your password once to sign in. It is never saved.")).toBeVisible();
    await expect(dialog.getByText("goes against LinkedIn's terms")).toBeVisible();
    await expect(dialog.getByText("Sync preferences")).toBeVisible();
    await expect(dialog.getByText("Advanced: proxy")).toBeVisible();
  });

  test("connects with an email, then shows the account", async ({ page }) => {
    const api = newApi({ script: [attempt("starting"), attempt("succeeded", { accountId: "acc1" })] });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Signing in to LinkedIn" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Ada Lovelace is connected.")).toBeVisible();

    const start = callsTo(api, "POST", /^\/linkedin-accounts\/connect$/)[0];
    expect(start.body).toMatchObject({ identifier: "ada@example.com", password: "Sup3r-Secret-Pw", syncMode: "synex_only" });
    expect(typeof start.body?.timezone).toBe("string");
    // The password is sent once and never again.
    expect(api.calls.filter((c) => JSON.stringify(c.body ?? {}).includes("Sup3r-Secret-Pw"))).toHaveLength(1);

    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByText("Ada Lovelace", { exact: true })).toBeVisible();
    await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  });

  test("accepts a phone number and rejects text that is neither email nor phone", async ({ page }) => {
    const api = newApi({ script: [attempt("starting"), attempt("succeeded", { accountId: "acc1" })] });
    await openConnect(page, api);
    await fillCredentials(page, "415 555 0123");
    await submit(page);
    await expect(page.getByText("Enter an email address, or a phone number with country code like +14155550123.")).toBeVisible();
    expect(callsTo(api, "POST", /connect$/)).toHaveLength(0);

    await page.getByLabel("Email or phone").fill("+1 415 555 0123");
    await submit(page);
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 15_000 });
    expect(callsTo(api, "POST", /^\/linkedin-accounts\/connect$/)[0].body).toMatchObject({ identifier: "+1 415 555 0123" });
  });

  test("the sync preference is private by default and can be changed", async ({ page }) => {
    const api = newApi({ script: [attempt("succeeded", { accountId: "acc1" })] });
    await openConnect(page, api);
    await page.getByText("Sync preferences").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Only conversations from Synex campaigns")).toBeChecked();
    await expect(dialog.getByText("Only the person who connects an account can change this later.")).toBeVisible();
    await dialog.getByLabel("All LinkedIn conversations").check();
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 15_000 });
    expect(callsTo(api, "POST", /^\/linkedin-accounts\/connect$/)[0].body).toMatchObject({ syncMode: "all" });
  });

  test("pasting a proxy URL fills the fields, tests it, and can be cleared", async ({ page }) => {
    const api = newApi({ script: [attempt("succeeded", { accountId: "acc1" })] });
    await openConnect(page, api);
    const dialog = page.getByRole("dialog");
    await dialog.getByText("Advanced: proxy").click();
    await expect(dialog.getByText("A proxy is optional and mainly useful for agencies running many accounts.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Test connection" })).toBeDisabled();

    await dialog.getByLabel("Paste a proxy URL").fill("socks5://user:pa%40ss@proxy.example.com:1080");
    await expect(dialog.getByLabel("Protocol")).toHaveValue("socks5");
    await expect(dialog.getByLabel("Host")).toHaveValue("proxy.example.com");
    await expect(dialog.getByLabel("Port")).toHaveValue("1080");
    await expect(dialog.getByLabel("Username (optional)")).toHaveValue("user");
    await expect(dialog.getByLabel("Proxy password (optional)")).toHaveValue("pa@ss");
    await expect(dialog.getByLabel("Paste a proxy URL")).toHaveValue("");

    await dialog.getByRole("button", { name: "Test connection" }).click();
    await expect(dialog.getByText("Proxy works. Exit IP 203.0.113.7 (NL), 142 ms.")).toBeVisible();
    expect(callsTo(api, "POST", /proxy-test$/)[0].body).toEqual({ proxyUrl: "socks5://user:pa%40ss@proxy.example.com:1080" });

    await dialog.getByLabel("Host").fill("other.example.com");
    await expect(dialog.getByText("Proxy works.")).toBeHidden();

    await dialog.getByRole("button", { name: "Connect without a proxy" }).click();
    await expect(dialog.getByLabel("Host")).toHaveValue("");
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 15_000 });
    expect(callsTo(api, "POST", /^\/linkedin-accounts\/connect$/)[0].body).not.toHaveProperty("proxyUrl");
  });

  test("a failed proxy test shows the specific reason", async ({ page }) => {
    const api = newApi({
      proxyTest: () => ({ ok: false, error: { code: "proxy_rejected", message: "The proxy refused the connection. Check the username and password." } }),
    });
    await openConnect(page, api);
    const dialog = page.getByRole("dialog");
    await dialog.getByText("Advanced: proxy").click();
    await dialog.getByLabel("Paste a proxy URL").fill("http://proxy.example.com:8080");
    await dialog.getByRole("button", { name: "Test connection" }).click();
    await expect(dialog.getByText("Test failed. The proxy refused the connection. Check the username and password.")).toBeVisible();
  });

  test("a verification code: one wrong code, then the right one", async ({ page }) => {
    const api = newApi({
      script: [attempt("starting"), attempt("awaiting_code", { challenge: { type: "email_code", hint: "We sent a code to a***@example.com." } })],
      onCode: (code, state) => {
        state.script =
          code === "482913"
            ? [attempt("starting"), attempt("succeeded", { accountId: "acc1" })]
            : [attempt("starting"), attempt("awaiting_code", { challenge: { type: "email_code" }, error: { code: "invalid_credentials", message: "That code was not accepted. Enter a new code." } })];
      },
    });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Enter your verification code" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("LinkedIn emailed you a verification code.")).toBeVisible();
    await expect(page.getByText("We sent a code to a***@example.com.")).toBeVisible();
    await expect(page.getByLabel("Email code")).toBeFocused();

    await page.getByLabel("Email code").fill("12ab");
    await page.getByRole("button", { name: "Verify code" }).click();
    await expect(page.getByText("Enter the code using digits only.")).toBeVisible();

    await page.getByLabel("Email code").fill("000000");
    await page.getByRole("button", { name: "Verify code" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "That code was not accepted. Enter a new code." })).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Email code").fill("482913");
    await page.getByRole("button", { name: "Verify code" }).click();
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 15_000 });
    expect(callsTo(api, "POST", /\/code$/).map((c) => c.body?.code)).toEqual(["000000", "482913"]);
  });

  test("app approval shows a waiting state that continues on its own", async ({ page }) => {
    const api = newApi({ script: [attempt("awaiting_app_approval"), attempt("awaiting_app_approval"), attempt("succeeded", { accountId: "acc1" })] });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Approve the sign-in in your LinkedIn app" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("This window continues on its own.")).toBeVisible();
    await expect(page.getByRole("status").first()).toHaveText("Approve the sign-in in your LinkedIn app.");
    await expect(page.getByRole("heading", { name: "Account connected" })).toBeVisible({ timeout: 20_000 });
  });

  test("manual verification explains what to do and stops polling", async ({ page }) => {
    const api = newApi({ script: [attempt("awaiting_manual_verification")] });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "LinkedIn needs you to verify this sign-in" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Synex will not complete it for you.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open LinkedIn" })).toHaveAttribute("rel", /noopener/);
    const polls = callsTo(api, "GET", /\/connect\/a1$/).length;
    await page.waitForTimeout(4500);
    expect(callsTo(api, "GET", /\/connect\/a1$/)).toHaveLength(polls);
  });

  test("invalid credentials return to the form with the identifier kept and no password", async ({ page }) => {
    const api = newApi({ script: [attempt("failed", { error: { code: "invalid_credentials", message: "LinkedIn did not accept that email, phone number or password." } })] });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "LinkedIn did not accept those details" })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByLabel("Email or phone")).toHaveValue("ada@example.com");
    await expect(page.getByLabel("LinkedIn password")).toHaveValue("");
  });

  test("closing the dialog mid-attempt cancels the attempt", async ({ page }) => {
    const api = newApi({ script: [attempt("starting"), attempt("awaiting_code", { challenge: { type: "sms_code" } })] });
    await openConnect(page, api);
    await fillCredentials(page);
    await submit(page);
    await expect(page.getByRole("heading", { name: "Enter your verification code" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel("Text message code")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect.poll(() => callsTo(api, "DELETE", /\/connect\/a1$/).length).toBe(1);
  });

  test("pausing an account and editing its limit", async ({ page }) => {
    const api = newApi({ accounts: [account()] });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await expect(page.getByText("12 of 50")).toBeVisible();

    await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
    await page.getByRole("menuitem", { name: "Pause sending" }).click();
    await expect(page.getByText("Paused", { exact: true })).toBeVisible();
    expect(callsTo(api, "PATCH", /acc1$/)[0].body).toEqual({ paused: true });

    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Daily action limit").fill("500");
    await dialog.getByRole("button", { name: "Save changes" }).click();
    await expect(dialog.getByText("Enter a whole number from 0 to 200. 0 pauses the account.")).toBeVisible();
    await expect(dialog.getByText("Ceiling 200 a day")).toBeVisible();
    await dialog.getByLabel("Daily action limit").fill("30");
    await dialog.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByText("12 of 30")).toBeVisible();
    expect(callsTo(api, "PATCH", /acc1$/)[1].body).toEqual({ dailyActionLimit: 30 });
  });

  test("a limit of 0 reads as paused, never as unlimited, and the ceilings show beside the field", async ({ page }) => {
    const api = newApi({ accounts: [account()] });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Ceiling 200 a day")).toBeVisible();
    await expect(dialog.getByText(/40 connection requests a day\s+\(150 a week\), 100 messages, 80 profile\s+visits and 50 follows a day/)).toBeVisible();
    await dialog.getByLabel("Daily action limit").fill("0");
    await expect(dialog.getByText("Paused for this action: the account sends nothing until you raise the limit.")).toBeVisible();
    await dialog.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    expect(callsTo(api, "PATCH", /acc1$/)[0].body).toEqual({ dailyActionLimit: 0 });
    await expect(page.getByText("Paused for this action")).toBeVisible();
    await expect(page.getByText("12 of 0")).toHaveCount(0);
  });

  test("the sync preference is read-only for someone who did not connect the account", async ({ page }) => {
    const api = newApi({ accounts: [account({ canChangeSyncMode: false, syncMode: "all" })] });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("All LinkedIn conversations")).toBeChecked();
    await expect(dialog.getByLabel("All LinkedIn conversations")).toBeDisabled();
    await expect(dialog.getByLabel("Only conversations from Synex campaigns")).toBeDisabled();
    await expect(dialog.getByText("Only the person who connected this account can change this.")).toBeVisible();
  });

  test("the account owner can change the sync preference and see a saved proxy is hidden", async ({ page }) => {
    const api = newApi({ accounts: [account({ proxyConfigured: true })] });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("A proxy is set. Its address is not shown.")).toBeVisible();
    await dialog.getByLabel("All LinkedIn conversations").check();
    await dialog.getByRole("button", { name: "Connect without a proxy" }).click();
    await expect(dialog.getByText("The proxy will be removed when you save.")).toBeVisible();
    await dialog.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    expect(callsTo(api, "PATCH", /acc1$/)[0].body).toEqual({ proxyUrl: null, syncMode: "all" });
  });

  test("disconnecting asks first and states what is kept and removed", async ({ page }) => {
    const api = newApi({ accounts: [account()] });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
    await page.getByRole("menuitem", { name: "Disconnect" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Disconnect Ada Lovelace?" })).toBeVisible();
    await expect(dialog.getByText("removes the saved LinkedIn session")).toBeVisible();
    await expect(dialog.getByText("keeps the account's name, its campaigns, conversations and activity history")).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    expect(callsTo(api, "DELETE", /acc1$/)).toHaveLength(0);

    await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
    await page.getByRole("menuitem", { name: "Disconnect" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Disconnect" }).click();
    await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
    expect(callsTo(api, "DELETE", /acc1$/)).toHaveLength(1);
  });

  test("a reconnect link can be created for sending to the account owner", async ({ page }) => {
    await mockApi(page, newApi({ accounts: [account({ status: "needs_reconnect", pausedReason: "LinkedIn signed this account out. Reconnect it to resume sending." })] }));
    await page.goto("/linkedin-accounts");
    await expect(page.getByText("LinkedIn signed this account out. Reconnect it to resume sending.")).toBeVisible();
    await page.getByRole("button", { name: "More actions for Ada Lovelace" }).click();
    await page.getByRole("menuitem", { name: "Send a link so the owner reconnects it" }).click();
    await expect(page.getByRole("textbox", { name: "Reconnect link" })).toHaveValue("http://localhost:5173/reconnect/tok123");
    await expect(page.getByText("The link works once and expires on")).toBeVisible();
  });

  test("fits a 360px screen: no sideways scroll on the list, the dialogs or the reconnect page", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    await mockApi(page, newApi({ accounts: [account({ proxyConfigured: true })] }));
    await page.goto("/linkedin-accounts");
    await expect(page.getByText("Ada Lovelace", { exact: true })).toBeVisible();
    expect(await noOverflow()).toBe(true);
    await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
    await page.getByRole("dialog").getByText("Advanced: proxy").click();
    expect(await noOverflow()).toBe(true);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    expect(await noOverflow()).toBe(true);
    await page.goto("/reconnect/tok123");
    await expect(page.getByRole("heading", { name: "Reconnect Ada Lovelace" })).toBeVisible();
    expect(await noOverflow()).toBe(true);
  });

  test("a failed list load shows a retry", async ({ page }) => {
    const api = newApi({ listStatus: 500 });
    await mockApi(page, api);
    await page.goto("/linkedin-accounts");
    await expect(page.getByRole("alert").filter({ hasText: "The server is unavailable." })).toBeVisible();
    api.listStatus = 200;
    api.accounts = [account()];
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText("Ada Lovelace", { exact: true })).toBeVisible();
  });
});

test.describe("public reconnect page", () => {
  test.setTimeout(60_000);

  test("a valid link names the account and runs the flow without extra options", async ({ page }) => {
    const api = newApi({ script: [attempt("starting"), attempt("succeeded", { accountId: "acc1" })] });
    await mockApi(page, api);
    await page.goto("/reconnect/tok123");
    await expect(page.getByRole("heading", { name: "Reconnect Ada Lovelace" })).toBeVisible();
    await expect(page.getByText("This link works once and expires on")).toBeVisible();
    await expect(page.getByText("Sync preferences")).toHaveCount(0);
    await expect(page.getByText("Advanced: proxy")).toHaveCount(0);
    await expect(page.getByLabel("Time zone")).toHaveCount(0);

    await page.getByLabel("Email or phone").fill("+14155550123");
    await page.getByLabel("LinkedIn password").fill("Sup3r-Secret-Pw");
    await page.getByRole("button", { name: "Connect LinkedIn account" }).click();
    await expect(page.getByRole("heading", { name: "Account reconnected" })).toBeVisible({ timeout: 15_000 });
    const start = callsTo(api, "POST", /^\/reconnect\/tok123\/connect$/)[0];
    expect(start.body).toEqual({ identifier: "+14155550123", password: "Sup3r-Secret-Pw" });
  });

  test("an expired or used link explains what to do", async ({ page }) => {
    await mockApi(page, newApi({ linkInfo: { status: 404, body: { detail: "This reconnect link is invalid or has expired." } } }));
    await page.goto("/reconnect/old-token");
    await expect(page.getByRole("heading", { name: "This link has expired or was already used" })).toBeVisible();
    await expect(page.getByText("Ask the person who shared it for a new link.")).toBeVisible();
    await expect(page.getByLabel("Email or phone")).toHaveCount(0);
  });
});
