import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* The Smart sequence: a tree of actions with If branches, voice notes, zoom and full screen. The API is mocked; nothing is sent. */

type Api = ReturnType<typeof newApi>;

const open = async (page: Page, over: Parameters<typeof newApi>[0] = {}) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], ...over });
  await mockApi(page, api);
  await page.goto("/campaigns/cb1/edit?step=2");
  await expect(page.getByRole("heading", { name: "Sequence", level: 2 })).toBeVisible();
  return api;
};
const toSmart = async (page: Page) => {
  await page.getByRole("button", { name: "Smart", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Switch to Smart" }).click();
};
const add = async (page: Page, where: string, item: string) => {
  await page.getByRole("button", { name: where }).click();
  await page.getByRole("menuitem", { name: new RegExp(item) }).click();
};
const lastUpdate = (api: Api) => callsTo(api, "POST", /^\/campaigns$/).filter((c) => (c.body as { action?: string })?.action === "update").at(-1)?.body as { sequenceMode: string; steps: { id: string; type: string; parentStepId: string | null; branchCondition: { branch: string } | null; config: Record<string, unknown> | null }[] };

test("switching to Smart asks first, keeps every step, and Classic is where it was", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("button", { name: "Classic", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Smart", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Switch to Smart?" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: "Classic", exact: true })).toHaveAttribute("aria-pressed", "true");
  await toSmart(page);
  await expect(page.getByRole("button", { name: "Smart", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Campaign start")).toBeVisible();
  const main = page.getByRole("list", { name: "Main sequence" });
  await expect(main.getByRole("heading", { level: 3 })).toHaveText(["Send connection request", "Wait", "Send message", "End"]);
  await expect(page.getByRole("list", { name: "Sequence steps" })).toHaveCount(0);
});

test("the Add action menu lists every node type and says why one cannot be added", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  const menu = page.getByRole("menu");
  for (const name of ["Send connection request", "Send message", "Send follow-up", "Send voice note", "Send InMail", "Send free InMail", "View profile", "Follow profile", "Like a post", "Withdraw invite", "Wait", "If connection", "Is active on LinkedIn"]) {
    await expect(menu.getByRole("menuitem", { name })).toHaveCount(1);
  }
  await expect(menu.getByRole("menuitem", { name: /Send connection request/ })).toHaveAttribute("aria-disabled", "true");
  await expect(menu.getByText("A sequence has one connection request.")).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: /Send voice note/ })).not.toHaveAttribute("aria-disabled", "true"); // a message precedes it in this list
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  await expect(page.getByRole("menuitem", { name: /Send voice note/ })).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText(/A voice note goes to a connection/)).toBeVisible(); // nothing before it, so a voice note has no certain connection yet
});

test("an If step splits into two branches, each with its own Add action and a closed list when it ends in a condition", async ({ page }) => {
  const api = await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await expect(page.getByRole("heading", { name: "Connected", level: 4 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Not connected", level: 4 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add action to the sequence" })).toHaveCount(0); // the main list now ends in the condition
  await add(page, "Add action to the yes branch", "Send message");
  await add(page, "Add action to the no branch", "Like a post");
  await expect(page.getByRole("list", { name: "Yes branch" }).getByRole("heading", { level: 3 })).toHaveText(["Send message"]);
  await expect(page.getByRole("list", { name: "No branch" }).getByRole("heading", { level: 3 })).toHaveText(["Like a post"]);
  await expect(page.getByLabel("Wait up to")).toHaveValue("15");
  await page.getByLabel("Wait up to").fill("10");
  await expect.poll(() => lastUpdate(api)?.steps.length, { timeout: 8000 }).toBeGreaterThan(5);
  const saved = lastUpdate(api);
  const condition = saved.steps.find((s) => s.type === "if_connected")!;
  expect(condition.config).toEqual({ waitDays: 10 });
  const yes = saved.steps.find((s) => s.type === "message" && s.parentStepId)!;
  const no = saved.steps.find((s) => s.type === "like_post")!;
  expect([yes.parentStepId, yes.branchCondition]).toEqual([condition.id, { branch: "yes" }]);
  expect([no.parentStepId, no.branchCondition]).toEqual([condition.id, { branch: "no" }]);
  expect(saved.sequenceMode).toBe("smart");
  expect(condition.id.startsWith("new-")).toBe(true); // a new step is saved under a temporary id the server replaces
});

test("Next stays off while a node is not ready, says which and why, and comes back when it is", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "Send InMail");
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await expect(page.getByText("Next is off: Send message: write the message.")).toBeVisible();
  await expect(page.getByRole("note").filter({ hasText: "not ready" })).toContainText("Send InMail: write the message.");
  const nodes = page.getByRole("article", { name: "Send InMail" });
  await nodes.getByLabel("InMail subject").fill("Quick question");
  await nodes.getByLabel("Send InMail text").fill("Hello {{first_name}}");
  await page.getByRole("article", { name: "Send message" }).getByLabel("Send message text").fill("Thanks for connecting");
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  await expect(page.getByText(/Next is off/)).toHaveCount(0);
});

test("zoom, full screen and clear all work, and Escape leaves full screen", async ({ page }) => {
  await open(page);
  await toSmart(page);
  const level = page.getByRole("status", { name: "Zoom level" });
  await expect(level).toHaveText("100%");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(level).toHaveText("125%");
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Zoom out" }).click();
  await expect(level).toHaveText("75%");
  await page.getByRole("button", { name: "Full screen" }).click();
  await expect(page.getByRole("region", { name: "Sequence graph, full screen" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Sequence graph, full screen" })).toHaveCount(0);
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Keep it" }).click();
  await expect(page.getByRole("list", { name: "Main sequence" }).getByRole("heading", { level: 3 })).toHaveCount(4);
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear all" }).click();
  await expect(page.getByRole("list", { name: "Main sequence" }).getByRole("heading", { level: 3 })).toHaveCount(0);
});

test("switching back to Classic names what it will remove", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "Like a post");
  await page.getByRole("button", { name: "Classic", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("removes the like a post step");
  await dialog.getByRole("button", { name: "Switch and remove them" }).click();
  await expect(page.getByRole("list", { name: "Sequence steps" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Like a post" })).toHaveCount(0);
});

test("a voice note: only where a connection is certain, direct upload with a preview, and the sender readiness panel", async ({ page }) => {
  await open(page);
  await page.getByLabel("Campaign name").fill("Voice");
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  await expect(page.getByText("Send voice note: record or upload the audio.").first()).toBeVisible();
  const node = page.getByRole("article", { name: "Send voice note" });
  await expect(node.getByLabel("Language and accent")).toHaveValue("en-US");
  await expect(node.getByText(/The same recording goes to everyone/)).toBeVisible();
  await node.getByLabel("Voice note file").setInputFiles({ name: "hello.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF0000WAVEfmt ") });
  await expect(node.getByText(/hello\.wav, 3 seconds/)).toBeVisible();
  await expect(node.getByLabel("Voice note preview")).toBeVisible();
  await expect(node.getByText("Ada Lovelace:")).toContainText("daily voice-note limit is 0");
  await expect(page.getByText(/Send voice note: record or upload/)).toHaveCount(0);
});

test("an AI voice note: the script is counted, the estimate is free, and the engine's absence is explained", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  const node = page.getByRole("article", { name: "Send voice note" });
  await node.getByLabel("AI assisted: write a script and let a voice read it").check();
  await node.getByLabel("Script").fill("Hi, it is Sam. Thank you for connecting.");
  await expect(node.getByTestId("voice-estimate")).toContainText("Free: made on this computer. About 12 seconds. Cost: $0.");
  await expect(node.getByText(/The voice engine is not set up for English \(US\)/)).toBeVisible();
  await expect(node.getByText(/Missing: the piper program/)).toBeVisible();
  await expect(node.getByRole("button", { name: "Make the audio" })).toBeDisabled();
  await expect(node.getByText(/\d+ of 1000 characters/)).toBeVisible();
});

test("with the engine installed the audio is made from the script, and editing the script asks for new audio", async ({ page }) => {
  await open(page, { voice: { ttsReady: true, made: null, readiness: [{ accountId: "a1", name: "Ada Lovelace", ready: true, reasons: [], roomToday: 20 }] } });
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  const node = page.getByRole("article", { name: "Send voice note" });
  await node.getByLabel("AI assisted: write a script and let a voice read it").check();
  await node.getByLabel("Script").fill("Hello there");
  await node.getByRole("button", { name: "Make the audio" }).click();
  await expect(node.getByText(/voice-note\.wav, 12 seconds/)).toBeVisible();
  await expect(node.getByText("Ada Lovelace:")).toContainText("ready, 20 left today");
  await node.getByLabel("Script").fill("Hello there again");
  await expect(node.getByText("No audio yet.")).toBeVisible();
  await expect(page.getByText(/Send voice note: make the audio from the script/).first()).toBeVisible();
});

test("keyboard: the menu opens from the Add action button, arrows choose, Enter adds, Escape returns focus", async ({ page }) => {
  await open(page);
  await toSmart(page);
  const addButton = page.getByRole("button", { name: "Add action to the sequence" });
  await addButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(addButton).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Main sequence" }).getByRole("heading", { level: 3 })).toHaveCount(5);
  // Every node's controls are reachable by Tab, in reading order, with names.
  const names: string[] = [];
  await page.getByRole("button", { name: "Zoom out" }).focus();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    names.push(await page.evaluate(() => (document.activeElement?.getAttribute("aria-label") || document.activeElement?.textContent || "").trim().slice(0, 40)));
  }
  expect(names).toContain("Zoom in");
  expect(names.some((n) => /^Remove /.test(n))).toBe(true);
});
