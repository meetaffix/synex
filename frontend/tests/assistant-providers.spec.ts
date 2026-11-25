import { test, expect, type Page } from "@playwright/test";
import { openAdvanced } from "./advanced";
import { callsTo, mockApi, newApi } from "./mock-api";

/* Choosing what answers in the assistant panel: Deepgram (default) or local models (Ollama, Whisper, Piper). The API is mocked; no model runs. */

const open = async (page: Page, over: (api: ReturnType<typeof newApi>) => void = () => undefined) => {
  const api = newApi();
  over(api);
  await mockApi(page, api);
  return api;
};

test("settings lists both providers with cost, where they run, licence and what is ready, and choosing local really switches", async ({ page }) => {
  const api = await open(page);
  await page.goto("/settings");
  await openAdvanced(page);
  const choice = page.getByTestId("provider-choice");
  await expect(choice.getByRole("radio", { name: "Deepgram voice agent" })).toBeChecked();
  await expect(choice).toContainText("Paid per minute. Runs on Deepgram's servers.");
  await expect(choice).toContainText("Free. Runs on This computer or network. Licence: Ollama MIT, Whisper MIT, Piper MIT");
  const parts = choice.getByRole("list", { name: "Local models parts" });
  await expect(parts).toContainText("Language model (Ollama): ready.");
  await expect(parts).toContainText("Speech to text (Whisper): not ready. Not set up. Missing: the faster-whisper package");
  await expect(parts).toContainText("Voice (Piper): not ready.");
  await choice.getByRole("radio", { name: "Local models" }).click(); // the choice follows the saved setting, so it changes once the server agrees
  await expect(choice.getByRole("radio", { name: "Local models" })).toBeChecked();
  expect(callsTo(api, "PUT", /\/assistant\/settings$/)[0].body).toEqual({ provider: "local" });
});

test("local cannot be chosen while the language model is not running, and the old choice stays with the reason shown", async ({ page }) => {
  await open(page, (api) => { api.syncStatus = "ollama-off"; });
  await page.goto("/settings");
  await openAdvanced(page);
  const choice = page.getByTestId("provider-choice");
  await choice.getByRole("radio", { name: "Local models" }).click(); // the choice follows the saved setting, so it changes once the server agrees
  await expect(page.getByText(/The local language model is not ready, so the assistant cannot switch to it/)).toBeVisible();
  await expect(choice.getByRole("radio", { name: "Deepgram voice agent" })).toBeChecked();
});

test("with local models chosen the panel answers through the local endpoint, shows confirmation cards, and never opens a Deepgram session", async ({ page }) => {
  const api = await open(page, (a) => { a.assistant.provider = "local"; });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Assistant" }).or(page.getByLabel("Assistant", { exact: true }).last());
  await page.getByPlaceholder("Type a message").fill("Which conversations need a reply?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Two conversations need a reply.")).toBeVisible();
  await expect(page.getByTestId("proposal-card")).toContainText("Add 1 company to the do-not-contact list.");
  expect(callsTo(api, "POST", /\/assistant\/local\/chat$/)).toHaveLength(1);
  expect(callsTo(api, "POST", /\/assistant\/session$/)).toHaveLength(0);
  expect(callsTo(api, "POST", /\/proposals\/p1\/confirm$/)).toHaveLength(0); // a card needs the click
  await expect(panel).toBeVisible();
});

test("the microphone in local mode says when Whisper is not set up instead of doing nothing", async ({ page }) => {
  await open(page, (a) => { a.assistant.provider = "local"; });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(page.getByRole("button", { name: "Speak" })).toBeVisible();
  await page.getByRole("button", { name: "Speak" }).click();
  await expect(page.getByText(/Speech to text \(Whisper\) is not set up on this computer/)).toBeVisible();
});
