import { test, expect } from "@playwright/test";
import { openAdvanced } from "./advanced";
import { callsTo, mockApi, newApi } from "./mock-api";

/* The free local-model assistant card in Settings. The API is mocked; no model runs. */

test("it says the model is ready, answers a typed request, and a proposed change needs a click", async ({ page }) => {
  const api = newApi();
  await mockApi(page, api);
  await page.goto("/settings");
  await openAdvanced(page);
  await expect(page.getByText("Free local model", { exact: true })).toBeVisible();
  await expect(page.getByText("Ready: llama3.2 is running.")).toBeVisible();
  await page.getByLabel("Ask the local assistant").fill("Which conversations need a reply?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Two conversations need a reply.")).toBeVisible();
  const card = page.getByRole("group", { name: "Confirmation needed" });
  await expect(card).toContainText("Add 1 company to the do-not-contact list.");
  expect(callsTo(api, "POST", /\/proposals\/p1\/confirm$/)).toHaveLength(0); // nothing applied yet
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Done.")).toBeVisible();
  expect(callsTo(api, "POST", /\/proposals\/p1\/confirm$/)).toHaveLength(1);
});

test("when the local model is not running it says how to start it and the box is disabled", async ({ page }) => {
  const api = newApi();
  api.syncStatus = "ollama-off";
  await mockApi(page, api);
  await page.goto("/settings");
  await openAdvanced(page);
  await expect(page.getByText(/Ollama is not running/)).toBeVisible();
  await expect(page.getByLabel("Ask the local assistant")).toBeDisabled();
});
