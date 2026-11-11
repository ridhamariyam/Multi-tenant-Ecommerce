import { defineConfig } from "@playwright/test";

/**
 * Runs against an already running stack (see README in this folder).
 * Uses the installed Google Chrome, so no browser download is needed.
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    channel: process.env.E2E_BROWSER_CHANNEL ?? "chrome",
    // Local rehearsals use Caddy's own certificate authority.
    ignoreHTTPSErrors: process.env.E2E_IGNORE_HTTPS_ERRORS === "1",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
