import { defineConfig } from "@playwright/test";
import { API_URL, APP_URL } from "./tests/support";

const python = process.platform === "win32" ? String.raw`.venv\Scripts\python.exe` : ".venv/bin/python";

// Both servers are started here, never reused: an already-running server on these ports could be pointed at the
// real API or the real database.
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 45000,
  globalSetup: "./tests/global-setup.ts",
  webServer: [
    {
      command: `${python} tests/browser_server.py`,
      cwd: "../backend",
      url: "http://127.0.0.1:8011/health",
      env: { PYTHONPATH: "." },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // PW_PREVIEW=1 runs the specs against the production build served by vite preview instead of the dev server.
      command: process.env.PW_PREVIEW ? "npx vite build && npx vite preview --port 5174 --host 127.0.0.1 --strictPort" : "npx vite --port 5174 --host 127.0.0.1 --strictPort",
      url: APP_URL,
      // The specs use the built-in sign-in and a mocked API: an empty key keeps Clerk mode off even when frontend/.env has one.
      env: { VITE_API_URL: API_URL, VITE_CLERK_PUBLISHABLE_KEY: "" },
      reuseExistingServer: false,
      timeout: process.env.PW_PREVIEW ? 240_000 : 60_000,
    },
  ],
  use: {
    baseURL: APP_URL,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
});
