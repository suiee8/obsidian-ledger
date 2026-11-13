import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

import { API, importSample, SAMPLE_PATH } from "./helpers";

const MEXC_PATH = resolve(process.cwd(), "..", "samples", "mexc_futures_order_history_normalized.csv");

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    results.violations.map((violation) =>
      `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`,
    ),
  ).toEqual([]);
}

test("imports the sample file from the Import screen", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(SAMPLE_PATH);

  const preview = page.locator(".import-preview");
  await expect(preview.getByRole("heading", { name: "What we found" })).toBeVisible();
  await expect(preview).toContainText("synthetic_preview.csv");
  await preview.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Imported synthetic_preview\.csv/ })).toBeVisible();
});

test("MEXC import shows capabilities and unavailable performance accessibly", async ({ page }) => {
  const reset = await page.request.post(`${API}/api/wipe`, {
    data: { confirm: "delete all my data" },
  });
  if (!reset.ok()) throw new Error(`Could not reset isolated E2E workspace: ${await reset.text()}`);

  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(MEXC_PATH);

  const preview = page.getByRole("region", { name: "What we found" });
  await expect(preview).toContainText("944 rows");
  await expect(preview).toContainText("P&L: not found");
  await expect(preview).toContainText("Price: not found");
  await expect(preview).toContainText("Hour-only timestamps");
  await expect(preview).toContainText("truncated");
  await expect(preview).toContainText("Exact duplicate rows");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expectNoA11yViolations(page);
  }

  await preview.getByRole("button", { name: "Import", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Imported mexc_futures_order_history_normalized\.csv/ }),
  ).toBeVisible();
  await expect(page.locator("section[aria-labelledby='result-title'] dd").first()).toHaveText("476");
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await page.getByRole("button", { name: "Analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Performance metrics unavailable" })).toBeVisible();
  await expect(page.getByText(/Not available: this file has no P&L or prices/)).toBeVisible();
  await expect(page.getByText("Net P&L", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Win rate", { exact: true })).toHaveCount(0);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expectNoA11yViolations(page);
  }
});

test("the dashboard renders headline numbers and the equity chart", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");

  await expect(page.locator(".kpi-strip")).toBeVisible();
  await expect(page.getByText("Net P&L", { exact: true })).toBeVisible();
  await expect(page.locator(".chart-equity canvas")).toBeVisible();
});

test("the trades table scrolls to the last loaded rows", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");
  await page.getByRole("button", { name: "Trades", exact: true }).click();

  await expect(page.locator(".grid-body").first()).toBeVisible();
  await page.locator(".grid-scroll").evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  // The table reports how many rows it has, so the test does not depend on what other specs imported.
  const total = Number(await page.getByRole("table", { name: "Trades" }).getAttribute("aria-rowcount"));
  expect(total).toBeGreaterThanOrEqual(1000);
  const last = page.locator(`[role="row"][aria-rowindex="${total}"]`);
  await expect(last).toBeVisible();
  // A row that is still a placeholder has no cells. A loaded row shows its trade.
  await expect(last.locator(".cell").first()).toBeVisible();
});

test("a symbol filter changes the dashboard request and shows as a chip", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");
  await expect(page.locator(".kpi-strip")).toBeVisible();

  const [response] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().includes("/api/dashboard") && candidate.url().includes("symbol=NVDA"),
    ),
    page.getByLabel("Add symbol filter").selectOption("NVDA"),
  ]);
  expect(response.ok()).toBeTruthy();
  await expect(page.locator(".filter-group .chip-button", { hasText: "NVDA" })).toBeVisible();
});
