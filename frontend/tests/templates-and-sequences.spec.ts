import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, campaign, inboxItem, mockApi, newApi } from "./mock-api";

/* Saved replies, template insertion, sequence templates and importing a shared sequence. The API is mocked. */

const tpl = (id: string, name: string, category: string, body: string, shortcut: string | null = null) => ({ id, name, category, body, shortcut, usageCount: 0, replyRate: 0, createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z" });

test("a template can have a shortcut, which the card shows, and a duplicate shortcut's error is shown as written", async ({ page }) => {
  const api = newApi({ templates: [tpl("t1", "Thanks", "reply", "Thanks for replying!", "thanks")] });
  await mockApi(page, api);
  await page.goto("/templates");
  await expect(page.getByRole("heading", { name: /Thanks/ }).first()).toContainText("/thanks");
  await page.getByRole("button", { name: /New template/ }).first().click();
  await page.getByLabel("Template name").fill("Another");
  await page.getByLabel("Shortcut (optional)").fill("later");
  await page.getByRole("dialog").getByRole("textbox").last().fill("Let us talk later.");
  await page.getByRole("button", { name: "Create template" }).click();
  await expect.poll(() => (callsTo(api, "POST", /^\/templates$/)[0]?.body as { shortcut?: string })?.shortcut).toBe("later");
});

test("in the inbox a saved reply is inserted from the list and /shortcut plus a space expands it", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], inbox: [inboxItem("c1", "Ann Archer")], templates: [tpl("t1", "Thanks", "reply", "Thanks for replying!", "thanks"), tpl("t2", "Intro", "first_message", "Not a reply")],
    messages: [{ id: "m1", direction: "inbound", body: "Hello", sentAt: "2026-11-16T08:00:00Z", deliveryStatus: "sent" }] });
  await mockApi(page, api);
  await page.goto("/inbox");
  await page.getByRole("list", { name: "Conversations" }).getByRole("button", { name: /Ann Archer/ }).first().click();
  const options = await page.getByLabel("Insert a saved reply").locator("option").allTextContents();
  expect(options).toEqual(["Saved replies", "/thanks: Thanks"]); // only reply templates are offered here
  await page.getByLabel("Insert a saved reply").selectOption({ label: "/thanks: Thanks" });
  await expect(page.getByLabel("Reply", { exact: true })).toHaveValue("Thanks for replying!");
  await page.getByLabel("Reply", { exact: true }).fill("");
  await page.getByLabel("Reply", { exact: true }).pressSequentially("Hi /thanks ");
  await expect(page.getByLabel("Reply", { exact: true })).toHaveValue("Hi Thanks for replying!");
});

test("a saved template is offered in the message editor, and a sequence file is imported as a draft", async ({ page }) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], templates: [tpl("t3", "Short note", "connection", "Hi {{first_name}}, let us connect.")] });
  await mockApi(page, api);
  await page.goto("/campaigns/cb1/edit?step=2");
  await page.getByRole("button", { name: /^Send connection request\s/ }).click();
  await page.getByLabel("Insert a saved template into Send connection request text").selectOption({ label: "Short note" });
  await expect(page.getByRole("textbox", { name: "Send connection request text", exact: true })).toHaveValue("Hi {{first_name}}, let us connect.");
});

test("a sequence file is imported as a draft, and a file that is not a sequence is refused with the reason", async ({ page }) => {
  await mockApi(page, newApi({ accounts: [account("a1", "Ada Lovelace")] }));
  await page.goto("/campaigns");
  await page.waitForLoadState("networkidle"); // the page must finish loading before a file is chosen
  await page.getByLabel("Import a sequence file").setInputFiles({ name: "bad.json", mimeType: "application/json", buffer: Buffer.from("{\"hello\":1}") });
  await expect(page.getByText("That is not a Synex sequence file.")).toBeVisible();
  await page.getByLabel("Import a sequence file").setInputFiles({ name: "x.synex-sequence.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify({ synexSequence: 1, name: "Shared", steps: [{ type: "message", message: "hi" }] })) });
  await expect(page).toHaveURL(/\/campaigns\/cb1\/edit\?step=2/);
});
