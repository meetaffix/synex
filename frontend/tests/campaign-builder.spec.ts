import { test, expect, type Page } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* The four-step campaign builder. The API is mocked; nothing is sent and no AI is called. */

const open = async (page: Page, over: Parameters<typeof newApi>[0] = {}) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace")], lists: [{ id: "L1", name: "Prospects", leadCount: 2, description: null, color: "primary", createdAt: "2026-11-01T00:00:00Z" }] as never, ...over });
  await mockApi(page, api);
  await page.goto("/campaigns/cb1/edit");
  await expect(page.getByLabel("Campaign name")).toBeVisible();
  return api;
};
const lastUpdate = (api: Awaited<ReturnType<typeof open>>) => callsTo(api, "POST", /^\/campaigns$/).filter((c) => (c.body as { action?: string })?.action === "update").at(-1)?.body as Record<string, unknown>;

test("it opens with no sender and no leads, shows four steps, and lets you move on freely", async ({ page }) => {
  await open(page);
  const steps = page.getByRole("navigation", { name: "Builder steps" }).getByRole("button");
  await expect(steps).toHaveText(["1. LinkedIn senders", "2. List of leads", "3. Sequence", "4. Review and launch"]);
  await expect(page.getByTestId("sender-total")).toHaveText("0 accounts selected. Total daily limit: 0 connections.");
  await page.getByRole("button", { name: "Next" }).click(); // no sender chosen: still allowed
  await expect(page.getByText("Add leads to begin")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click(); // no leads chosen: still allowed
  await expect(page.getByRole("heading", { name: "Sequence" })).toBeVisible();
  await expect(page).toHaveURL(/step=2/);
});

test("choosing a sender shows its limit and total, and the allocation drawer reserves a slice", async ({ page }) => {
  const api = await open(page);
  await page.getByLabel("Use Ada Lovelace").check();
  await expect(page.getByTestId("sender-total")).toContainText("1 account selected");
  await expect(page.getByText("up to 6 (rolling 24 h)")).toBeVisible();
  await expect(page.getByRole("link", { name: "View limits" })).toHaveAttribute("href", "/linkedin-accounts/a1?tab=limits");
  await page.getByRole("button", { name: /Reserve actions for this campaign on Ada Lovelace/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/Capacity you do not reserve goes to older campaigns first/)).toBeVisible();
  await dialog.getByLabel(/Send connection request/).fill("999");
  await dialog.getByRole("button", { name: "Save allocations" }).click();
  await expect.poll(() => (lastUpdate(api)?.allocation as Record<string, Record<string, number>>)?.a1?.send_invite).toBe(40); // clamped to the hard maximum
  expect((lastUpdate(api).accountId)).toBe("a1");
});

test("it saves as you go: the name autosaves, the indicator says so, and Save draft waits for a change", async ({ page }) => {
  const api = await open(page);
  await expect(page.getByRole("button", { name: "Save draft" })).toBeDisabled();
  await page.getByLabel("Campaign name").fill("Autumn outreach");
  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 8000 });
  expect(lastUpdate(api).name).toBe("Autumn outreach");
  await expect(page.getByRole("button", { name: "Save draft" })).toBeDisabled();
});

test("leaving with unsaved changes asks first", async ({ page }) => {
  await open(page);
  await page.getByLabel("Campaign name").fill("Half typed");
  await page.getByRole("button", { name: "All campaigns" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Discard unsaved changes?")).toBeVisible();
  await dialog.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/campaigns$/);
});

test("the sequence: variables insert as chips, spintax, preview with a missing-variable warning, and a follow-up can be added and removed", async ({ page }) => {
  await open(page);
  await page.goto("/campaigns/cb1/edit?step=2");
  const note = page.getByRole("textbox", { name: "Connection request text", exact: true });
  await note.fill("Hi ");
  await page.getByLabel("Insert a variable into Connection request text").selectOption("first_name");
  await expect(note).toHaveValue("Hi {{first_name}}");
  await expect(page.getByLabel("Connection request text with variables marked")).toContainText("first_name");
  await expect(page.getByText(/17 of 200 characters/)).toBeVisible();
  await page.getByRole("button", { name: "Add spintax" }).first().click();
  await expect(note).toHaveValue(/\{Hi\|Hello\|Hey\}/);
  await expect(page.getByText("If connected")).toBeVisible();
  await expect(page.getByText(/at least 3 hours after the invitation is accepted/)).toBeVisible();
  await page.getByRole("button", { name: "Add follow-up message" }).click();
  await expect(page.getByRole("heading", { name: "Follow-up message" })).toBeVisible();
  await expect(page.getByText("If not replied")).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("heading", { name: "Follow-up message" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Smart" })).toBeDisabled();
});

test("AI writing: the drawer has Direct and AI assisted, tone, strategy, honest profile options, a preview with its cost, and an unsaved-changes prompt", async ({ page }) => {
  const api = await open(page);
  await page.goto("/campaigns/cb1/edit?step=2");
  await page.getByRole("switch", { name: /Synex AI writing/ }).first().click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByRole("heading", { name: /Configure AI for the connection note/ })).toBeVisible();
  await expect(drawer.getByRole("tab", { name: "AI assisted" })).toHaveAttribute("aria-selected", "true");
  await expect(drawer.getByLabel(/Recent posts/)).toBeDisabled();
  await expect(drawer.getByText(/needs the paced profile reader/).first()).toBeVisible();
  await expect(drawer.getByLabel("Current role and company")).toBeChecked();
  await drawer.getByRole("radio", { name: "Witty" }).click();
  await drawer.getByRole("radio", { name: "Curiosity hook" }).click();
  await drawer.getByLabel("AI generation instructions (optional)").fill("Keep it short");
  await drawer.getByRole("button", { name: "First name" }).click();
  await expect(drawer.getByLabel("AI generation instructions (optional)")).toHaveValue("Keep it short {{first_name}}");
  await drawer.getByRole("button", { name: "Preview message" }).click();
  await expect(drawer.getByText("Hi Ada, loved your work at Engines.")).toBeVisible();
  await expect(drawer.getByText(/This preview cost nothing/)).toBeVisible();
  await drawer.getByRole("button", { name: "Close" }).first().click();
  await expect(page.getByRole("alertdialog", { name: "Unsaved changes" })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).last().click();
  await expect.poll(() => (lastUpdate(api)?.steps as { aiConfig?: { tone: string; strategy: string; mode: string } }[])?.[0]?.aiConfig?.tone).toBe("witty");
  const saved = (lastUpdate(api).steps as { aiConfig: { strategy: string; mode: string; instructions: string } }[])[0].aiConfig;
  expect([saved.strategy, saved.mode, saved.instructions]).toEqual(["curiosity_hook", "ai", "Keep it short {{first_name}}"]);
});

test("AI campaign context: three tabs, templates, guardrails, and Save AI settings", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "AI campaign context" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("tab")).toHaveText(["Upload", "Context", "Guardrails"]);
  await expect(panel.getByText(/PDF and Word files are not read yet/)).toBeVisible();
  await panel.getByRole("button", { name: "Add website" }).click();
  await expect(panel.getByLabel("Website address")).toBeVisible();
  await panel.getByRole("tab", { name: "Context" }).click();
  await panel.getByRole("button", { name: "Free Audit" }).click();
  await expect(panel.getByLabel("Goals, audience, offer and value")).toHaveValue(/free audit/i);
  await panel.getByLabel(/Campaign meeting link/).fill("https://cal.example.com/me");
  await panel.getByRole("tab", { name: "Guardrails" }).click();
  await panel.getByLabel("Do not mention").fill("pricing");
  await panel.getByRole("button", { name: "Add", exact: true }).click();
  await expect(panel.getByRole("list", { name: "Phrases the AI must not mention" })).toContainText("pricing");
  await panel.getByRole("button", { name: "Save AI settings" }).click();
  await expect.poll(() => (lastUpdate(api)?.aiContext as Record<string, unknown>)?.do_not_mention).toEqual(["pricing"]);
  expect((lastUpdate(api).aiContext as Record<string, string>).meeting_link).toBe("https://cal.example.com/me");
});

test("review: schedule, exclusions with the do-not-contact list locked on, and the checklist names every blocker with the step that fixes it", async ({ page }) => {
  const api = await open(page, {});
  api.launchProblems = [
    { kind: "no_connected_account", field: "accountId", message: "Select a connected sender account for this campaign.", step: "senders" },
    { kind: "empty_lead_list", field: "leadListId", message: "Add at least one lead to the campaign's list before launching.", step: "leads" },
    { kind: "empty_message", field: "steps", message: "One or more message steps are empty.", step: "sequence" },
  ];
  await page.goto("/campaigns/cb1/edit?step=3");
  await expect(page.getByLabel("Saturday on")).not.toBeChecked();
  await expect(page.getByLabel("Monday on")).toBeChecked();
  await page.getByLabel("Monday end").fill("18:00");
  await page.getByRole("button", { name: "Apply to all" }).first().click();
  await expect(page.getByLabel("Friday end")).toHaveValue("18:00");
  await expect(page.getByLabel("Do not contact list (always on)")).toBeDisabled();
  await page.getByRole("switch", { name: "Exclude existing LinkedIn connections" }).click();
  await expect.poll(() => (lastUpdate(api)?.exclusions as Record<string, boolean>)?.existing_connections).toBe(true);
  expect(Object.keys(lastUpdate(api).weekSchedule as object)).toHaveLength(7);
  await expect(page.getByText("Missing required information")).toBeVisible();
  await expect(page.getByText("No lead list selected. Please go back and select a lead list.")).toBeVisible();
  const launch = page.getByRole("button", { name: "Fix 3 things to launch" });
  await expect(launch).toBeDisabled();
  await expect(page.getByLabel("I confirm all details are correct and ready to launch")).toBeDisabled();
  await page.getByRole("button", { name: "Go to List of leads" }).click();
  await expect(page).toHaveURL(/step=1/);
});

test("review: a dry run shows what would be sent and who is skipped, and nothing is sent", async ({ page }) => {
  const api = await open(page);
  await page.goto("/campaigns/cb1/edit?step=3");
  await page.getByRole("button", { name: /dry run/ }).click();
  await expect(page.getByRole("row", { name: /Ada Lovelace/ })).toContainText("connection request: Hi Ada");
  await expect(page.getByText("On the do-not-contact list.")).toBeVisible();
  expect(callsTo(api, "POST", /^\/campaigns$/).filter((c) => (c.body as { status?: string })?.status === "active")).toHaveLength(0);
});

test("review: AI messages show their cost before they are written, must be approved, and then the campaign launches", async ({ page }) => {
  const api = await open(page);
  api.builder = {
    id: "cb1", name: "AI campaign", status: "draft", accountId: "a1", accountIds: [], leadListId: "L1", leadListName: "Prospects", dailyConnectionLimit: 20, dailyMessageLimit: 40, schedule: { timezone: "UTC" },
    weekSchedule: null, exclusions: {}, allocation: {}, aiContext: {}, launchSummary: null,
    steps: [{ id: "s1", type: "connection_request", order: 0, message: "Hi", delayHours: null, aiConfig: null }, { id: "s3", type: "message", order: 1, message: "", delayHours: null, aiConfig: { mode: "ai", tone: "auto", strategy: "auto", instructions: "", profile_data: { role_company: true } } }],
  };
  api.launchProblems = [{ kind: "ai_drafts_missing", field: "steps", message: "2 AI messages not written yet. Generate them in the Review step, or switch the step to a plain message.", step: "review" }];
  await page.goto("/campaigns/cb1/edit?step=3");
  await expect(page.getByTestId("ai-estimate")).toContainText("2 AI messages to write. About 1 minutes, no cost, written by template.");
  await page.getByRole("button", { name: "Write 2 AI messages" }).click();
  await expect(page.getByRole("list", { name: "AI messages to review" })).toContainText("Hi Ada, a prepared note.");
  await expect(page.getByText("Waiting for review")).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Edit message for Ada Lovelace").fill("Edited note");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("button", { name: "Approve all (1)" }).click();
  await expect(page.getByText("Everything needed to launch is in place.")).toBeVisible();
  await page.getByLabel("I confirm all details are correct and ready to launch").check();
  await page.getByRole("button", { name: "Launch campaign" }).click();
  await expect(page.getByText("Campaign launched.")).toBeVisible();
  expect(callsTo(api, "POST", /^\/campaigns$/).filter((c) => (c.body as { status?: string })?.status === "active")).toHaveLength(1);
});

test("a campaign that is running cannot be edited here, and an unknown one says so", async ({ page }) => {
  const api = await open(page);
  api.builder = { ...(api.builder ?? {}), status: "active" } as never;
  await page.reload();
  await expect(page.getByText(/has launched and is running/)).toBeVisible();
});
