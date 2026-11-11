import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

import { importSample } from "./helpers";

// These specs import more files into the shared test database, so they run last (Playwright runs
// files in name order) and each one narrows the app to its own account with a filter.
const PLANTED = resolve(process.cwd(), "..", "samples", "coach_planted.csv");
const NOISE = resolve(process.cwd(), "..", "samples", "coach_noise.csv");

async function onlyAccount(page: Page, account: string) {
  const request = page.waitForRequest(
    (candidate) =>
      candidate.url().includes("/api/coach/stream") && candidate.url().includes(`account=${account}`),
  );
  await page.getByLabel("Add account filter").selectOption(account);
  await request;
  await expect(page.getByRole("complementary", { name: "Coach" })).toHaveAttribute("data-phase", "ready");
}

async function importThroughTheScreen(page: Page, file: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(file);
  const preview = page.locator(".import-preview");
  await expect(preview).toBeVisible();
  await preview.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Imported/ })).toBeVisible();
}

test("importing a file starts the Coach, streams its steps, and shows the report", async ({ page }) => {
  await importThroughTheScreen(page, PLANTED);

  const coach = page.getByRole("complementary", { name: "Coach" });
  await expect(coach).toBeVisible();
  const steps = coach.getByRole("region", { name: "Report steps" });
  for (const label of ["Reading", "Mapping", "Cleaning", "Computing", "Finding leaks", "Writing report"]) {
    await expect(steps.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(coach).toHaveAttribute("data-phase", "ready");
  await onlyAccount(page, "main");
  await expect(coach.getByText("Top leaks")).toBeVisible();
  await expect(coach.getByText(/Revenge-style re-entries/).first()).toBeVisible();
  await expect(coach.getByRole("button", { name: "Run again" })).toBeEnabled();
});

test("clicking a trade chip scrolls to the trade and highlights it", async ({ page }) => {
  await importThroughTheScreen(page, PLANTED);
  await onlyAccount(page, "main");
  const coach = page.getByRole("complementary", { name: "Coach" });

  const chip = coach.getByRole("button", { name: /Show trade/ }).first();
  const label = (await chip.getAttribute("aria-label")) ?? "";
  const tradeId = /Show trade (\S+) in/.exec(label)?.[1];
  expect(tradeId).toBeTruthy();
  await chip.click();

  await expect(page.getByRole("heading", { name: "Trades", exact: true })).toBeVisible();
  const row = page.locator(`.grid-body.is-highlight[data-trade-id="${tradeId}"]`);
  await expect(row).toBeVisible();
  // The row is inside the visible part of the scroll area, not just in the DOM.
  const inView = await row.evaluate((element) => {
    const area = element.closest(".grid-scroll")?.getBoundingClientRect();
    const box = element.getBoundingClientRect();
    return area !== undefined && box.top >= area.top - 1 && box.bottom <= area.bottom + 1;
  });
  expect(inView).toBe(true);
});

test("Apply as filter on each leak opens exactly the trades the finding counts", async ({ page }) => {
  await importThroughTheScreen(page, PLANTED);
  await onlyAccount(page, "main");
  const coach = page.getByRole("complementary", { name: "Coach" });
  const leaks = coach.getByRole("region", { name: "Top leaks" }).locator("[data-finding]");
  const ids = await leaks.evaluateAll((cards) => cards.map((card) => card.getAttribute("data-finding") ?? ""));
  expect(ids).toEqual(expect.arrayContaining(["beh~revenge", "beh~overtrading"]));
  expect(ids.some((id) => id.startsWith("seg~hour~"))).toBe(true);

  for (const id of ids) {
    // Start from a clean app each time, then narrow to the planted account like a user would.
    await page.goto("/");
    await page.getByRole("button", { name: "Coach", exact: true }).click();
    await onlyAccount(page, "main");
    const card = coach.getByRole("region", { name: "Top leaks" }).locator(`[data-finding="${id}"]`);
    const shown = ((await card.locator(".coach-numbers span").first().textContent()) ?? "").replace(" trades", "");
    await card.getByRole("button", { name: /^Apply as filter/ }).click();

    await expect(page.getByRole("heading", { name: "Trades", exact: true })).toBeVisible();
    await expect(page.locator(".trades-toolbar"), id).toContainText(`${shown} trades`);
    await expect(page.locator(".selection-note"), id).toContainText(`${shown} trades behind`);
  }
});

test("a noise journal gets no leaks and says so", async ({ page }) => {
  await importThroughTheScreen(page, NOISE);
  await onlyAccount(page, "noise");
  const coach = page.getByRole("complementary", { name: "Coach" });
  await expect(coach.getByText(/No leak cleared the false-discovery filter/).first()).toBeVisible();
  await expect(coach.getByRole("heading", { name: /Unproven/ })).toBeVisible();
});

test("the Coach drawer has no WCAG 2.1 AA violations", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  const coach = page.getByRole("complementary", { name: "Coach" });
  await expect(coach).toHaveAttribute("data-phase", "ready");
  const results = await new AxeBuilder({ page })
    .include(".coach-drawer")
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const problems = results.violations.map((violation) => {
    const sample = violation.nodes
      .slice(0, 2)
      .map((node) => node.target.join(" "))
      .join(" | ");
    return `${violation.id} (${violation.nodes.length}) ${sample}: ${violation.help}`;
  });
  expect(problems).toEqual([]);
});

test("the Coach opens and closes from the keyboard", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "Coach", exact: true });
  await toggle.focus();
  await page.keyboard.press("Enter");
  const coach = page.getByRole("complementary", { name: "Coach" });
  await expect(coach).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(coach).toHaveCount(0);
});
