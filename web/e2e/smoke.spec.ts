import { expect, test } from "@playwright/test";

import { importSample, SAMPLE_PATH } from "./helpers";

test("imports the sample file from the Import screen", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(SAMPLE_PATH);

  const preview = page.locator(".import-preview");
  await expect(preview.getByRole("heading", { name: /synthetic_preview\.csv/ })).toBeVisible();
  await preview.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Imported synthetic_preview\.csv/ })).toBeVisible();
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
