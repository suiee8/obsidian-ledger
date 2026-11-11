import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { API, importSample } from "./helpers";

// Screenshots for review go to docs/screens. Each file is named screen-width.png.
const OUT = resolve(process.cwd(), "..", "docs", "screens");
const WIDTHS = [1440, 1024, 390];
const DASHBOARD = "**/api/dashboard**";

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

for (const width of WIDTHS) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: width >= 1024 ? 1000 : 844 } });

    test("import, dashboard, and trades with data", async ({ page, request }) => {
      await importSample(request);
      await page.goto("/");

      await page.getByRole("button", { name: "Import", exact: true }).click();
      await expect(page.locator('input[type="file"]')).toBeAttached();
      await page.screenshot({ path: `${OUT}/import-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Dashboard", exact: true }).click();
      await expect(page.locator(".chart-equity canvas")).toBeVisible();
      await page.screenshot({ path: `${OUT}/dashboard-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Trades", exact: true }).click();
      await expect(page.locator(".grid-body").first()).toBeVisible();
      await page.screenshot({ path: `${OUT}/trades-${width}.png` });
    });

    test("dashboard empty state", async ({ page, request }) => {
      await importSample(request);
      // A filter that matches nothing gives the same response a fresh database gives.
      const empty = await request.get(`${API}/api/dashboard?symbol=NO_SUCH_SYMBOL`);
      expect(empty.ok()).toBeTruthy();
      const body = await empty.text();
      await page.route(DASHBOARD, (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body }),
      );
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Import a journal to see your edge." })).toBeVisible();
      await page.screenshot({ path: `${OUT}/dashboard-empty-${width}.png`, fullPage: true });
    });

    test("dashboard loading state", async ({ page, request }) => {
      await importSample(request);
      // The request never completes, so the page stays on its loading skeleton.
      await page.route(DASHBOARD, () => undefined);
      await page.goto("/");
      await expect(page.locator('[aria-label="Loading dashboard"]')).toBeVisible();
      await page.screenshot({ path: `${OUT}/dashboard-loading-${width}.png`, fullPage: true });
    });

    test("dashboard error state", async ({ page, request }) => {
      await importSample(request);
      await page.route(DASHBOARD, (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "database_busy",
              message: "The local database is busy. Try again in a moment.",
              details: {},
            },
          }),
        }),
      );
      await page.goto("/");
      await expect(page.getByRole("alert")).toContainText("The dashboard could not load");
      await page.screenshot({ path: `${OUT}/dashboard-error-${width}.png`, fullPage: true });
    });
  });
}
