import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// Each run gets a fresh data folder, so tests never depend on earlier runs. Playwright starts the
// API and the built web app itself. The web app must be built first (`pnpm -C web test:e2e` does).
const dataDir = mkdtempSync(join(tmpdir(), "ledger-e2e-"));

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    // Uses the Microsoft Edge that is already installed, so no browser download is needed.
    channel: "msedge",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    // Without these, a locator that matches nothing waits for the whole test timeout.
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  webServer: [
    {
      command: "uv run --directory ../api uvicorn obsidian_ledger.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      // Keys live in memory for the run, never in your Windows Credential Manager. The mock below
      // is offered as an extra "Test model" provider; no real AI provider is ever contacted.
      env: {
        LEDGER_DATA_DIR: dataDir,
        LEDGER_LLM_SECRET_STORE: "memory",
        LEDGER_LLM_TEST_PROVIDER_URL: "http://127.0.0.1:11435/v1",
      },
      timeout: 120_000,
    },
    {
      // A scripted OpenAI-compatible model (api/tests/llm/mock_server.py). Standard library only.
      command: "uv run --directory ../api python tests/llm/mock_server.py --port 11435",
      url: "http://127.0.0.1:11435/v1/models",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm exec vite preview --host 127.0.0.1 --port 5173 --strictPort",
      url: "http://127.0.0.1:5173/",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
