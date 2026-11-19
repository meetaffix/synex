import { test, expect, type Page } from "@playwright/test";
import { callsTo, mockApi, newApi } from "./mock-api";

/* Speaking to the local assistant: the browser is given a fake microphone, Whisper is a stand-in in the mocked API. Its own file because the browser launch options are per file. */

test.use({ permissions: ["microphone"], launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] } });

const open = async (page: Page, over: (api: ReturnType<typeof newApi>) => void = () => undefined) => {
  const api = newApi();
  over(api);
  await mockApi(page, api);
  return api;
};
test("speaking is transcribed by Whisper and the words are answered like typed ones", async ({ page }) => {
  const api = await open(page, (a) => { a.assistant.provider = "local"; a.assistant.sttReady = true; });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(page.getByRole("button", { name: "Speak" })).toBeVisible();
  await expect.poll(() => callsTo(api, "GET", /assistant\/providers/).length).toBeGreaterThan(0);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Speak" }).click();
  await expect(page.getByRole("button", { name: "Stop and send" })).toBeVisible();
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "Stop and send" }).click();
  await expect(page.getByText("Two conversations need a reply.")).toBeVisible({ timeout: 15000 });
  expect(callsTo(api, "POST", /\/assistant\/local\/transcribe$/)).toHaveLength(1);
  expect((callsTo(api, "POST", /\/assistant\/local\/chat$/)[0].body as { text: string }).text).toBe("Which conversations need a reply?");
});

