/**
 * Test safety. The browser specs talk either to a mocked API or to the fixture server in
 * backend/tests/browser_server.py (port 8011, its own database). They must never reach the real local
 * API on port 8010, which serves backend/synex.db. This module is imported by the Playwright config and by
 * every mocked spec, and refuses to load if the configured API is the real one.
 */
export const API_URL = process.env.VITE_API_URL ?? "http://127.0.0.1:8011";
export const API_PORT = new URL(API_URL).port;
export const APP_URL = "http://127.0.0.1:5174";

const REAL_API_PORTS = ["8010"];

if (REAL_API_PORTS.includes(API_PORT)) {
  throw new Error(
    `Refusing to run browser tests against ${API_URL}: port ${API_PORT} is the real local API (backend/synex.db). ` +
      "Unset VITE_API_URL to use the fixture server on port 8011.",
  );
}
