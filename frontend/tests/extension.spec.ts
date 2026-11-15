import { test, expect, chromium } from "@playwright/test";
import path from "node:path";
test("browser extension captures an idea and opens official connection workflow", async () => {
  const extensionPath = path.resolve("../extension");
  const context = await chromium.launchPersistentContext("", {
    channel: "chromium",
    headless: true,
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
    ],
  });
  try {
    const worker =
      context.serviceWorkers()[0] ??
      (await context.waitForEvent("serviceworker"));
    const id = new URL(worker.url()).host;
    const popup = await context.newPage();
    await popup.goto(`chrome-extension://${id}/popup.html`);
    await popup.getByLabel("Workspace URL").fill("http://127.0.0.1:5174");
    await popup
      .getByLabel("Capture an idea")
      .fill("An idea captured by the browser companion.");
    const opened = context.waitForEvent("page");
    await popup.getByRole("button", { name: "Open in Content studio" }).click();
    const studio = await opened;
    await studio.waitForLoadState();
    await expect(
      studio.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
    await studio
      .getByLabel("Email", { exact: true })
      .fill("browser@example.com");
    await studio
      .getByLabel("Password", { exact: true })
      .fill("Browser-Test-Password!");
    await studio.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      studio.getByRole("heading", { name: "Content studio", exact: true }),
    ).toBeVisible();
    await expect(studio.getByLabel("Post", { exact: true })).toHaveValue(
      "An idea captured by the browser companion.",
    );
    await studio
      .getByRole("button", { name: "Save draft", exact: true })
      .click();
    await expect(
      studio.getByText("Draft saved", { exact: true }),
    ).toBeVisible();
    await popup.reload();
    await expect(popup.getByLabel("Capture an idea")).toHaveValue(
      "An idea captured by the browser companion.",
    );
    const connection = context.waitForEvent("page");
    await popup.getByRole("button", { name: "Connect LinkedIn" }).click();
    const accounts = await connection;
    await expect(
      accounts.getByRole("heading", { name: "Publishing connections", exact: true }),
    ).toBeVisible();
    await popup.getByLabel("Workspace URL").fill("javascript:alert(1)");
    await popup.getByRole("button", { name: "Sign in to SYNEX" }).click();
    await expect(popup.getByRole("status")).toHaveText(
      "Use HTTPS, or HTTP localhost for development.",
    );
    await popup.screenshot({ path: "test-results/extension-popup.png" });
  } finally {
    await context.close();
  }
});
