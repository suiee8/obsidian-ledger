import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { API } from "./helpers";

// The optional cloud AI layer, tested against the mock provider (api/tests/llm/mock_server.py) that
// the API offers as "Test model (mock)". Keys are kept in memory for the run.
const KEY = "e2e-test-key-123456";
const PLANTED = resolve(process.cwd(), "..", "samples", "coach_planted.csv");
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function put(request: APIRequestContext, path: string, data: Record<string, unknown>) {
  const response = await request.put(`${API}${path}`, { data });
  expect(response.ok(), await response.text()).toBe(true);
}

/** The steps a person takes in Settings: provider, key, model, consent. */
async function useMock(request: APIRequestContext) {
  await put(request, "/api/llm/config", { provider: "test" });
  await put(request, "/api/llm/key", { provider: "test", api_key: KEY });
  await put(request, "/api/llm/config", { model: "mock-coach", consent: true });
}

/** No provider at all: what a new install looks like. */
async function aiOff(request: APIRequestContext) {
  await request.delete(`${API}/api/llm/key/test`);
  await put(request, "/api/llm/config", { provider: "none" });
}
test.beforeAll(async ({ request }) => {
  const preview = await request.post(`${API}/api/imports/preview?filename=coach_planted.csv`, {
    data: readFileSync(PLANTED),
    headers: { "content-type": "text/csv" },
  });
  const { preview_id: id } = (await preview.json()) as { preview_id: string };
  await request.post(`${API}/api/imports/${id}/commit`, { data: {} });
});

// Later specs run with the AI off, as before.
test.afterAll(async ({ request }) => {
  await aiOff(request);
});

const coach = (page: Page) => page.getByRole("complementary", { name: "Coach" });

async function openCoach(page: Page, account?: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await expect(coach(page)).toHaveAttribute("data-phase", "ready");
  if (!account) return;
  const rerun = page.waitForRequest(
    (candidate) => candidate.url().includes("/api/coach/stream") && candidate.url().includes(`account=${account}`),
  );
  await page.getByLabel("Add account filter").selectOption(account);
  await rerun;
  await expect(coach(page)).toHaveAttribute("data-phase", "ready");
}

async function ask(page: Page, question: string) {
  const drawer = coach(page);
  await drawer.getByRole("tab", { name: "Ask the Coach" }).click();
  await drawer.getByLabel("Your question").fill(question);
  await drawer.getByRole("button", { name: "Ask", exact: true }).click();
}

test("with no AI provider set up, the computed report is complete and the AI layer says so", async ({
  page,
  request,
}) => {
  await aiOff(request);
  await openCoach(page);
  const drawer = coach(page);
  await expect(drawer.getByRole("region", { name: "AI summary" })).toContainText(
    "AI summary unavailable. No AI provider is set up.",
  );
  await expect(drawer.getByRole("heading", { name: "Top leaks" })).toBeVisible();
  await expect(drawer.getByRole("region", { name: "Verdict" })).toBeVisible();

  await drawer.getByRole("tab", { name: "Ask the Coach" }).click();
  await expect(drawer.getByText(/AI answers are unavailable. No AI provider is set up./)).toBeVisible();
  await expect(drawer.getByLabel("Your question")).toBeDisabled();

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const panel = page.getByRole("region", { name: "AI provider" });
  await expect(panel.getByRole("status")).toContainText("Off. Choose an AI provider in Settings.");
});

test("Settings sets up a provider with an API key, a model, and consent", async ({ page, request }) => {
  await aiOff(request);
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const panel = page.getByRole("region", { name: "AI provider" });
  await panel.getByRole("combobox", { name: /^Provider/ }).selectOption("test");
  await expect(panel.getByRole("status")).toContainText("Save an API key");

  // A wrong key is caught by the connection test before anything is saved.
  await panel.getByLabel("API key for Test model (mock)").fill("wrong-key-000000");
  await panel.getByRole("button", { name: "Test connection" }).click();
  await expect(panel.getByText(/did not accept the API key/)).toBeVisible();

  await panel.getByLabel("API key for Test model (mock)").fill(KEY);
  await panel.getByRole("button", { name: "Save key" }).click();
  await expect(panel.getByText(/API key saved in Windows Credential Manager \(…3456\)/)).toBeVisible();
  await expect(panel.getByRole("status")).toContainText("Choose a model");

  await panel.getByRole("combobox", { name: /^Model/ }).selectOption("mock-coach");
  await expect(panel.getByRole("status")).toContainText("Confirm in Settings");
  await panel.getByRole("button", { name: "Test connection" }).click();
  await expect(panel.getByText(/answered with mock-coach/)).toBeVisible();
  await panel.getByRole("checkbox", { name: /Send computed results to Test model/ }).check();
  await expect(panel.getByRole("status")).toContainText("Ready: Test model (mock), mock-coach.");
});
test("with a mock model, the summary appears and the chat answers, cites trades, and shows its tools", async ({
  page,
  request,
}) => {
  await useMock(request);
  await openCoach(page, "main");
  const drawer = coach(page);
  const summary = drawer.getByRole("region", { name: "AI summary" });
  await summary.getByRole("button", { name: "Write an AI summary" }).click();
  await expect(summary).toContainText("Every number matched a computed figure.");
  await expect(summary).toContainText("mock-coach");

  await ask(page, "What is my biggest leak?");
  const answers = drawer.getByRole("list", { name: "Questions and answers" });
  await expect(answers.getByText(/Revenge-style re-entries/).first()).toBeVisible();
  await expect(answers.getByText("Tool results used: 1")).toBeVisible();
  await expect(answers.getByText("From result #1").first()).toBeVisible();
  await expect(answers.getByText(/Numbers were checked against the tool results./)).toBeVisible();

  const chip = answers.getByRole("button", { name: /Show trade/ }).first();
  const tradeId = /Show trade (\S+) in/.exec((await chip.getAttribute("aria-label")) ?? "")?.[1];
  expect(tradeId).toBeTruthy();
  await chip.click();
  await expect(page.getByRole("heading", { name: "Trades", exact: true })).toBeVisible();
  await expect(page.locator(`.grid-body.is-highlight[data-trade-id="${tradeId}"]`)).toBeVisible();
});

test("Stop ends a slow answer at once", async ({ page, request }) => {
  await useMock(request);
  await openCoach(page);
  await ask(page, "A slow question, please");
  const drawer = coach(page);
  const stop = drawer.getByRole("button", { name: "Stop", exact: true });
  await expect(stop).toBeVisible();
  await stop.click();
  await expect(drawer.getByText("Stopped. No further model calls were made.")).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Ask", exact: true })).toBeVisible();
});

for (const width of [1440, 390]) {
  test.describe(`chat drawer at ${width} px`, () => {
    test.use({ viewport: { width, height: width >= 1024 ? 1000 : 844 } });

    test("has no WCAG 2.1 AA violations with an answer shown", async ({ page, request }) => {
      await useMock(request);
      await openCoach(page);
      await ask(page, "What is my biggest leak?");
      const drawer = coach(page);
      await expect(drawer.getByText(/Numbers were checked against the tool results./)).toBeVisible();
      await drawer.getByText(/Tool results used/).click(); // open the tool list too
      const results = await new AxeBuilder({ page }).include(".coach-drawer").withTags(WCAG).analyze();
      const problems = results.violations.map(
        (violation) =>
          `${violation.id} (${violation.nodes.length}) ${violation.nodes
            .slice(0, 2)
            .map((node) => node.target.join(" "))
            .join(" | ")}: ${violation.help}`,
      );
      expect(problems).toEqual([]);
    });
  });
}
