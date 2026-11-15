import { defineConfig } from "@playwright/test";
import { API_URL, APP_URL } from "./tests/support";

const python = process.platform === "win32" ? String.raw`.venv\Scripts\python.exe` : ".venv/bin/python";

// The browser extension opens the workspace the way a person would, so it is tested against a production
// build served by `vite preview` (no on-demand compilation), with the same fixture API as the main suite.
export default defineConfig({
  testDir: "./tests",
  testMatch: "extension.spec.ts",
  workers: 1,
  timeout: 45000,
  globalSetup: "./tests/global-setup-preview.ts",
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
      command: "npx vite build --outDir dist-e2e --emptyOutDir && npx vite preview --outDir dist-e2e --port 5174 --host 127.0.0.1 --strictPort",
      url: APP_URL,
      env: { VITE_API_URL: API_URL },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
  use: { baseURL: APP_URL, screenshot: "only-on-failure", trace: "retain-on-failure" },
  reporter: [["list"]],
});
