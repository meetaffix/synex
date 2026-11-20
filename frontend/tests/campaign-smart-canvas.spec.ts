import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* The Smart sequence as a node canvas (React Flow): nodes open a settings drawer, If steps split into labelled branches.
   The API is mocked; nothing is sent. */

type Api = ReturnType<typeof newApi>;

const open = async (page: Page, over: Parameters<typeof newApi>[0] = {}) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], ...over });
  await mockApi(page, api);
  await page.goto("/campaigns/cb1/edit?step=2");
  await expect(page.getByRole("heading", { name: "Sequence", level: 2 })).toBeVisible();
  return api;
};
const toSmart = async (page: Page) => {
  await expect(page.getByRole("region", { name: "Sequence graph canvas" })).toBeVisible();
};
const add = async (page: Page, where: string, item: string) => {
  await page.getByRole("button", { name: where }).click();
  await page.getByRole("menuitem", { name: new RegExp(item) }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
};
/** A step node on the canvas; its accessible name starts with the step's label. */
const node = (page: Page, label: string) => page.getByRole("button", { name: new RegExp(`^${label}\\s`) });
const nodes = (page: Page) => page.getByRole("button", { name: /Open settings$/ });
const openNode = async (page: Page, label: string) => {
  await node(page, label).first().click();
  const drawer = page.getByRole("dialog", { name: new RegExp(`Configure ${label.toLowerCase()}`) });
  await expect(drawer).toBeVisible();
  return drawer;
};
const lastUpdate = (api: Api) => callsTo(api, "POST", /^\/campaigns$/).filter((c) => (c.body as { action?: string })?.action === "update").at(-1)?.body as { sequenceMode: string; steps: { id: string; type: string; parentStepId: string | null; branchCondition: { branch: string } | null; config: Record<string, unknown> | null }[] };

test("the Add action menu lists every node type and says why one cannot be added", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  const menu = page.getByRole("menu");
  for (const name of ["Send connection request", "Send message", "Send follow-up", "Send voice note", "Send InMail", "Send free InMail", "View profile", "Follow profile", "Like a post", "Withdraw invite", "Wait", "If connection", "Is active on LinkedIn"]) {
    await expect(menu.getByRole("menuitem", { name: new RegExp(`^${name}`) })).toHaveCount(1);
  }
  await expect(menu.getByText("Takes back an invitation that is still waiting.")).toBeVisible(); // every action says in one line what it does
  await expect(menu.getByRole("menuitem", { name: /Send connection request/ })).toHaveAttribute("aria-disabled", "true");
  await expect(menu.getByText("A sequence has one connection request.")).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: /Send voice note/ })).not.toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  await expect(page.getByRole("menuitem", { name: /Send voice note/ })).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText(/A voice note goes to a connection/)).toBeVisible();
});

test("an If step splits into two labelled branches, each with its own Add action and a closed list when it ends in a condition", async ({ page }) => {
  const api = await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expect(page.getByText("Not connected", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add action to the sequence" })).toHaveCount(0);
  await add(page, "Add action to the yes branch", "Send message");
  await add(page, "Add action to the no branch", "Like a post");
  await expect(node(page, "Like a post")).toHaveCount(1);
  const drawer = await openNode(page, "If connection");
  await expect(drawer.getByLabel("Wait up to")).toHaveValue("15");
  await drawer.getByLabel("Wait up to").fill("10");
  await expect.poll(() => lastUpdate(api)?.steps.length, { timeout: 8000 }).toBeGreaterThan(5);
  const saved = lastUpdate(api);
  const condition = saved.steps.find((s) => s.type === "if_connected")!;
  expect(condition.config).toEqual({ waitDays: 10 });
  const yes = saved.steps.find((s) => s.type === "message" && s.parentStepId)!;
  const no = saved.steps.find((s) => s.type === "like_post")!;
  expect([yes.parentStepId, yes.branchCondition]).toEqual([condition.id, { branch: "yes" }]);
  expect([no.parentStepId, no.branchCondition]).toEqual([condition.id, { branch: "no" }]);
  expect(saved.sequenceMode).toBe("smart");
  expect(condition.id.startsWith("new-")).toBe(true);
});

test("Next stays off while a node is not ready, says which and why, and comes back when it is", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "Send InMail");
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
  await expect(page.getByText("Next is off: Send InMail: write the message.")).toBeVisible();
  await expect(page.getByRole("note").filter({ hasText: "not ready" })).toContainText("Send InMail: write the message.");
  const inmail = await openNode(page, "Send InMail");
  await inmail.getByLabel("InMail subject").fill("Quick question");
  await inmail.getByRole("textbox", { name: "Send InMail text", exact: true }).fill("Hello {{first_name}}");
  await inmail.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  await expect(page.getByText(/Next is off/)).toHaveCount(0);
});

test("the canvas has zoom and fit controls, full screen leaves with Escape, and clear all asks first", async ({ page }) => {
  await open(page);
  await toSmart(page);
  const canvas = page.getByRole("region", { name: "Sequence graph canvas" });
  await expect(canvas.getByRole("button", { name: "zoom in", exact: false })).toBeVisible();
  await expect(canvas.getByRole("button", { name: "zoom out", exact: false })).toBeVisible();
  await expect(canvas.getByRole("button", { name: "fit view", exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Full screen" }).click();
  await expect(page.getByRole("region", { name: "Sequence graph, full screen" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Sequence graph, full screen" })).toHaveCount(0);
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Keep it" }).click();
  await expect(nodes(page)).toHaveCount(4);
  await page.getByRole("button", { name: "Clear all" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear all" }).click();
  await expect(nodes(page)).toHaveCount(0);
});

test("a node opens a settings drawer on the right, Remove deletes it, and Escape closes the drawer", async ({ page }) => {
  await open(page);
  await toSmart(page);
  const drawer = await openNode(page, "Wait");
  await expect(drawer.getByLabel("Wait", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  const again = await openNode(page, "Wait");
  await again.getByRole("button", { name: "Remove step" }).click();
  await expect(node(page, "Wait")).toHaveCount(0);
  await expect(nodes(page)).toHaveCount(3);
});

test("a voice note: only where a connection is certain, direct upload with a preview, and the sender readiness panel", async ({ page }) => {
  await open(page);
  await page.getByLabel("Campaign name").fill("Voice");
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  await expect(page.getByText("Send voice note: record or upload the audio.").first()).toBeVisible();
  const drawer = await openNode(page, "Send voice note");
  await expect(drawer.getByLabel("Language and accent")).toHaveValue("en-US");
  await expect(drawer.getByText(/The same recording goes to everyone/)).toBeVisible();
  await drawer.getByLabel("Voice note file").setInputFiles({ name: "hello.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF0000WAVEfmt ") });
  await expect(drawer.getByText(/hello\.wav, 3 seconds/)).toBeVisible();
  await expect(drawer.getByLabel("Voice note preview")).toBeVisible();
  await expect(drawer.getByText("Ada Lovelace:")).toContainText("daily voice-note limit is 0");
  await expect(page.getByText(/Send voice note: record or upload/)).toHaveCount(0);
});

test("an AI voice note: the script is counted, the estimate is free, and the engine's absence is explained", async ({ page }) => {
  await open(page);
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  const drawer = await openNode(page, "Send voice note");
  await drawer.getByLabel("AI assisted: write a script and let a voice read it").check();
  await drawer.getByRole("textbox", { name: "Script" }).fill("Hi, it is Sam. Thank you for connecting.");
  await expect(drawer.getByTestId("voice-estimate")).toContainText("Free: made on this computer. About 12 seconds. Cost: $0.");
  await expect(drawer.getByText(/The voice engine is not set up for English \(US\)/)).toBeVisible();
  await expect(drawer.getByText(/Missing: the piper program/)).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Make the audio" })).toBeDisabled();
  await expect(drawer.getByText(/\d+ of 1000 characters/)).toBeVisible();
});

test("with the engine installed the audio is made from the script, and editing the script asks for new audio", async ({ page }) => {
  await open(page, { voice: { ttsReady: true, made: null, readiness: [{ accountId: "a1", name: "Ada Lovelace", ready: true, reasons: [], roomToday: 20 }] } });
  await toSmart(page);
  await add(page, "Add action to the sequence", "If connection");
  await add(page, "Add action to the yes branch", "Send voice note");
  const drawer = await openNode(page, "Send voice note");
  await drawer.getByLabel("AI assisted: write a script and let a voice read it").check();
  await drawer.getByRole("textbox", { name: "Script" }).fill("Hello there");
  await drawer.getByRole("button", { name: "Make the audio" }).click();
  await expect(drawer.getByText(/voice-note\.wav, 12 seconds/)).toBeVisible();
  await expect(drawer.getByText("Ada Lovelace:")).toContainText("ready, 20 left today");
  await drawer.getByRole("textbox", { name: "Script" }).fill("Hello there again");
  await expect(drawer.getByText("No audio yet.")).toBeVisible();
  await expect(drawer.getByText(/Send voice note: make the audio from the script/).first()).toBeVisible();
});

test("keyboard: the menu opens from the Add action button, arrows choose, Enter adds, Escape returns focus, nodes are reachable by Tab", async ({ page }) => {
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
  await expect(nodes(page)).toHaveCount(5);
  const first = node(page, "Send connection request");
  await first.focus();
  await expect(first).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: /Configure send connection request/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a message box offers variables as chips and spintax, and a small icon rewrites the text in a human voice, with Undo", async ({ page }) => {
  await open(page);
  await page.route(/\/campaigns\/cb1\/drafts\/rewrite$/, (route) => route.fulfill({ json: { text: "Hey {{first_name}}, loved your post.", provider: "deepgram", changed: true } }));
  const drawer = await openNode(page, "Send connection request");
  const box = drawer.getByRole("textbox", { name: "Send connection request text", exact: true });
  await box.fill("Dear ");
  await drawer.getByLabel("Insert a variable into Send connection request text").selectOption("first_name");
  await expect(drawer.getByLabel("Send connection request text with variables marked")).toContainText("first_name");
  await box.fill("I hope this message finds you well, {{first_name}}.");
  await expect(drawer.getByText("Synex AI writing")).toHaveCount(0);
  await drawer.getByRole("button", { name: /Rewrite Send connection request text to sound more human/ }).click();
  await expect(box).toHaveValue("Hey {{first_name}}, loved your post.");
  await expect(drawer.getByText("Rewritten in a plainer, more human voice.")).toBeVisible();
  await drawer.getByRole("button", { name: "Undo" }).click();
  await expect(box).toHaveValue("I hope this message finds you well, {{first_name}}.");
});

test("a new campaign's sequence starts empty, and the builder has no Classic, Templates, Webhook or second assistant button", async ({ page }) => {
  await open(page);
  for (const name of ["Classic", "Smart", "Templates", "Build with AI", "AI campaign context"]) await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Sequence settings: configure webhook/ })).toHaveCount(0);
});

test("for a list of people who are already connections, steps that exist to get connected are not offered, and ones already there are flagged", async ({ page }) => {
  await open(page, { lists: [{ id: "L1", name: "My connections", leadCount: 3, allConnections: true, description: null, color: "primary", createdAt: "2026-11-01T00:00:00Z" }] });
  await expect(page.getByText(/Send connection request: these people are already your connections/).first()).toBeVisible();
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  for (const [name, reason] of [["Send connection request", "already your connections"], ["Send InMail", "send a normal message"], ["Send free InMail", "send a normal message"], ["Withdraw invite", "no pending invitation"], ["If connection", "nothing to wait for"]] as const) {
    const item = page.getByRole("menuitem", { name: new RegExp(`^${name}`) });
    await expect(item).toHaveAttribute("aria-disabled", "true");
    await expect(item).toContainText(reason);
  }
  for (const name of ["Send message", "Send follow-up", "View profile", "Wait"]) await expect(page.getByRole("menuitem", { name: new RegExp(`^${name}`) })).not.toHaveAttribute("aria-disabled", "true");
});

test("for people who may not be connected, connection requests and InMail stay available", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Add action to the sequence" }).click();
  await expect(page.getByRole("menuitem", { name: /^Send InMail/ })).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("menuitem", { name: /^If connection/ })).not.toHaveAttribute("aria-disabled", "true");
});
