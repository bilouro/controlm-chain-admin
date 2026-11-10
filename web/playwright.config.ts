import { defineConfig, devices } from "@playwright/test";
import { ENVS_PORT, ENVS_URL, EXPORT_FILE } from "./tests/e2e/envs";

// The built UI served by `ctmchain serve` on a synthetic repository (scripts/e2e_server.py).
// CTMCHAIN_E2E_ASSISTANT=1 also starts Kilo and runs the assistant tests (a real model).
// A second server has a repository with one branch per environment (tests/e2e/environments).
const port = process.env.CTMCHAIN_E2E_PORT ?? "8799";
const python = process.env.CTMCHAIN_PYTHON ?? "../.venv/bin/python";
const withAssistant = process.env.CTMCHAIN_E2E_ASSISTANT === "1";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: withAssistant ? 600_000 : 30_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} scripts/e2e_server.py`,
      url: `http://127.0.0.1:${port}/api/repo`,
      timeout: 120_000,
      reuseExistingServer: false,
      // SIGTERM lets ctmchain serve stop the Kilo it started; SIGKILL would leave it running.
      gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `${python} scripts/e2e_server.py --environments`,
      url: `${ENVS_URL}/api/repo`,
      env: { CTMCHAIN_E2E_ENVS_PORT: ENVS_PORT, CTMCHAIN_E2E_EXPORT: EXPORT_FILE },
      timeout: 120_000,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
