import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { API } from "./helpers";

// Screenshots of the Coach drawer in each state, saved to docs/screens. These specs run after the
// others (Playwright runs files in name order) because they add the planted sample to the database.
const OUT = resolve(process.cwd(), "..", "docs", "screens");
const WIDTHS = [1440, 1024, 390];
const PLANTED = resolve(process.cwd(), "..", "samples", "coach_planted.csv");

test.beforeAll(async ({ request }) => {
  mkdirSync(OUT, { recursive: true });
  const preview = await request.post(`${API}/api/imports/preview?filename=coach_planted.csv`, {
    data: readFileSync(PLANTED),
    headers: { "content-type": "text/csv" },
  });
  const { preview_id: id } = (await preview.json()) as { preview_id: string };
  await request.post(`${API}/api/imports/${id}/commit`, { data: {} });
});

const coach = (page: Page) => page.getByRole("complementary", { name: "Coach" });

// Below 640 px the filters live in the Filters sheet, so they are changed through it. Wider
// screens change them in the top bar directly.
async function setFilters(page: Page, change: () => Promise<void>) {
  const width = page.viewportSize()?.width ?? 1440;
  if (width >= 640) {
    await change();
    return;
  }
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  await expect(sheet).toBeVisible();
  await change();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
}

async function openCoach(page: Page, change?: () => Promise<void>) {
  await page.goto("/");
  if (change) await setFilters(page, change);
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await expect(coach(page)).toBeVisible();
}

async function dateRange(page: Page, from: string, to: string) {
  await page.getByLabel("From date").fill(from);
  await page.getByLabel("To date").fill(to);
}

for (const width of WIDTHS) {
  test.describe(`Coach at ${width} px`, () => {
    test.use({ viewport: { width, height: width >= 1024 ? 1000 : 844 } });

    test("ready", async ({ page }) => {
      await openCoach(page, async () => {
        await page.getByLabel("Add account filter").selectOption("main");
      });
      await expect(coach(page)).toHaveAttribute("data-phase", "ready");
      await expect(coach(page).getByText("Top leaks")).toBeVisible();
      await page.screenshot({ path: `${OUT}/coach-ready-${width}.png` });
    });

    test("running", async ({ page }) => {
      // The stream never answers, so the drawer stays on its step timeline.
      await page.route("**/api/coach/stream**", () => undefined);
      await openCoach(page);
      await expect(coach(page)).toHaveAttribute("data-phase", "running");
      await page.screenshot({ path: `${OUT}/coach-running-${width}.png` });
    });

    test("fewer than 30 trades", async ({ page }) => {
      await openCoach(page, () => dateRange(page, "2024-01-02", "2024-01-03"));
      await expect(coach(page).getByText("Not enough trades yet")).toBeVisible();
      await page.screenshot({ path: `${OUT}/coach-few-trades-${width}.png` });
    });

    test("no trades", async ({ page }) => {
      await openCoach(page, () => dateRange(page, "2031-01-01", "2031-01-02"));
      await expect(coach(page).getByText("No trades to review")).toBeVisible();
      await page.screenshot({ path: `${OUT}/coach-empty-${width}.png` });
    });

    test("error", async ({ page }) => {
      await page.route("**/api/coach/stream**", (route) => route.abort());
      await openCoach(page);
      await expect(coach(page).getByRole("alert")).toBeVisible();
      await page.screenshot({ path: `${OUT}/coach-error-${width}.png` });
    });
  });
}
