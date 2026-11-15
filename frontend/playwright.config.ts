import { defineConfig } from "@playwright/test";
import { API_URL, APP_URL } from "./tests/support";

const python = process.platform === "win32" ? String.raw`.venv\Scripts\python.exe` : ".venv/bin/python";

// Both servers are started here, never reused: an already-running server on these ports could be pointed at the
// real API or the real database.
export default defineConfig({
  testDir: "./tests",
  // The extension spec runs against a production build: playwright.extension.config.ts.
  testIgnore: "extension.spec.ts",
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
      command: "npx vite --port 5174 --host 127.0.0.1 --strictPort",
      url: APP_URL,
      env: { VITE_API_URL: API_URL },
      reuseExistingServer: false,
      timeout: 60_000,
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
