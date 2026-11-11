import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { API, importSample, SAMPLE_PATH } from "./helpers";

// Analytics, Behavior, Simulator, and Settings. These specs only add data the sample already has
// and clean up what they change, so the specs that run after them see the same database.

async function openScreen(page: Page, name: string, heading: string) {
  await page.goto("/");
  await page.getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
}

/** Presses Tab until the locator has focus. Fails if it is not reached in `limit` presses. */
async function tabTo(page: Page, target: Locator, limit = 90) {
  for (let step = 0; step < limit; step += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error("The control was not reached with Tab.");
}

test.describe("Analytics", () => {
  test("explores segments, the constellation, streaks, fee drag, and the Monte Carlo fan", async ({
    page,
    request,
  }) => {
    await importSample(request);
    await openScreen(page, "Analytics", "Analytics");

    // Segment explorer: pick a dimension and a measure, and the table follows.
    const explorer = page.getByRole("region", { name: "Segment explorer" });
    await explorer.getByLabel("Group trades by").selectOption("setup");
    await explorer.getByLabel("Measure").selectOption("win_rate");
    await expect(explorer.getByRole("columnheader", { name: "Setup" })).toBeVisible();
    await expect(explorer.locator("tbody tr").first()).toBeVisible();
    await expect(explorer.locator("canvas")).toBeVisible();

    await expect(page.locator(".chart-scatter canvas").first()).toBeVisible();
    const streaks = page.getByRole("region", { name: "Streaks", exact: true });
    await expect(streaks.getByText("Longest winning run")).toBeVisible();
    const fees = page.getByRole("region", { name: "Fee drag", exact: true });
    await expect(fees.getByText("Total costs", { exact: true })).toBeVisible();

    const fan = page.getByRole("region", { name: "Monte Carlo fan" });
    await expect(fan.locator("canvas")).toBeVisible();
    await expect(fan.getByText("Chance of reaching")).toBeVisible();
  });

  test("a rectangle on the constellation opens exactly those trades in the Trades table", async ({
    page,
    request,
  }) => {
    await importSample(request);
    await openScreen(page, "Analytics", "Analytics");
    const chart = page.locator(".chart-scatter").first();
    await expect(chart.locator("canvas")).toBeVisible();
    await chart.scrollIntoViewIfNeeded(); // the mouse works in viewport coordinates
    await page.waitForTimeout(1200); // let the entrance animation finish before dragging
    const box = await chart.boundingBox();
    if (!box) throw new Error("The constellation has no size.");

    await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.15);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.85, { steps: 8 });
    await page.mouse.up();

    const status = page.getByText(/trades inside the rectangle/);
    await expect(status).toBeVisible();
    const inside = Number(/([\d,]+) trades inside/.exec((await status.textContent()) ?? "")?.[1]?.replace(/,/g, ""));
    expect(inside).toBeGreaterThan(0);

    await page.getByRole("button", { name: "Open these trades in the Trades table" }).click();
    await expect(page.getByRole("heading", { name: "Trades", exact: true })).toBeVisible();
    const note = page.locator(".selection-note");
    await expect(note).toContainText("the Trade Constellation");
    // The table shows as many trades as the rectangle held.
    await expect(page.locator(".trades-toolbar")).toContainText(`${inside.toLocaleString("en-US")} trades`);

    await note.getByRole("button", { name: "Show all trades" }).click();
    await expect(page.locator(".selection-note")).toHaveCount(0);
  });

  test("the same selection can be made without a mouse", async ({ page, request }) => {
    await importSample(request);
    await openScreen(page, "Analytics", "Analytics");
    await page.getByLabel("Net P&L at most").fill("-1");
    await page.getByRole("button", { name: "Open in the Trades table" }).click();
    await expect(page.locator(".selection-note")).toContainText("your date and value range");

    const expected = await request.post(`${API}/api/selections`, {
      data: { bounds: [{ field: "pnl", high: -1 }] },
    });
    const { count } = (await expected.json()) as { count: number };
    await expect(page.locator(".trades-toolbar")).toContainText(`${count.toLocaleString("en-US")} trades`);
  });
});

test.describe("Behavior", () => {
  test("shows the timelines, post-loss performance, and the Discipline Score formula", async ({
    page,
    request,
  }) => {
    await importSample(request);
    await openScreen(page, "Behavior", "Behavior");

    for (const title of ["Revenge timeline", "Tilt timeline", "Overtrading timeline"]) {
      const panel = page.getByRole("region", { name: title });
      await expect(panel).toBeVisible();
      await expect(panel.locator("canvas")).toBeVisible();
    }
    const postLoss = page.getByRole("region", { name: "Performance after a loss" });
    await expect(postLoss.getByRole("rowheader", { name: "After a win" })).toBeVisible();
    await expect(postLoss.getByRole("rowheader", { name: /revenge-style/ })).toBeVisible();

    const discipline = page.getByRole("region", { name: "Discipline Score" });
    await expect(discipline.getByRole("meter").first()).toBeVisible();
    await expect(discipline.getByText(/Sum of weight × component/)).toBeVisible();

    // The formula appears in a tooltip on keyboard focus, and Escape hides it.
    const tip = discipline.getByRole("button", { name: "How the Discipline Score is calculated" });
    await tip.focus();
    await expect(page.getByRole("tooltip")).toContainText("Discipline = 0.30");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await tip.hover();
    await expect(page.getByRole("tooltip")).toContainText("plan adherence");
  });
});

test.describe("Simulator", () => {
  test("shows the overfitting warning first, the point estimate next, and the interval last", async ({
    page,
    request,
  }) => {
    await importSample(request);
    // Hold back the interval request so the order is visible.
    await page.route("**/api/simulate", async (route) => {
      const body = route.request().postDataJSON() as { intervals?: boolean };
      if (body.intervals) await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });
    await openScreen(page, "Simulator", "Simulator");
    await expect(page.getByLabel("Overfitting warning")).toContainText("Rules chosen after looking");

    await page.getByLabel("Most trades per day").fill("2");
    const table = page.getByRole("region", { name: "Before and after table" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("rowheader", { name: "Net P&L" })).toBeVisible();
    await expect(page.getByText("Working out the interval")).toBeVisible();
    await expect(page.getByText(/with a 95% interval of/)).toBeVisible();
    await expect(page.getByText(/The interval (includes|excludes) zero/)).toBeVisible();
    await expect(page.locator(".chart-fan canvas")).toBeVisible();
    await expect(page.getByLabel("Overfitting warning")).toContainText("High risk of overfitting");

    await page.getByRole("button", { name: "Clear all rules" }).click();
    await expect(page.getByText("Set at least one rule")).toBeVisible();
  });
});

test.describe("Settings", () => {
  test("privacy defaults to aggregates only and the choice is kept", async ({ page, request }) => {
    await importSample(request);
    await openScreen(page, "Settings", "Settings");
    const privacy = page.getByRole("region", { name: "Privacy" });
    const aggregates = privacy.getByRole("checkbox", { name: /Aggregates only/ });
    const rows = privacy.getByRole("checkbox", { name: /individual trade rows/ });
    await expect(aggregates).toBeChecked();
    await expect(rows).toBeDisabled();

    await aggregates.uncheck();
    await expect(rows).toBeEnabled();
    await rows.check();
    await page.reload();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("checkbox", { name: /individual trade rows/ })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: /Aggregates only/ })).not.toBeChecked();

    await page.getByRole("checkbox", { name: /Aggregates only/ }).check();
    await expect(page.getByRole("checkbox", { name: /individual trade rows/ })).not.toBeChecked();
  });

  test("starting equity can be set and cleared", async ({ page, request }) => {
    await importSample(request);
    await openScreen(page, "Settings", "Settings");
    const panel = page.getByRole("region", { name: "Starting equity" });
    await panel.getByLabel("Starting equity").fill("25000");
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByText("Set to 25,000.00.")).toBeVisible();
    await panel.getByRole("button", { name: "Clear" }).click();
    await expect(panel.getByText("No starting equity is set.")).toBeVisible();
  });

  test("a column template can be renamed and deleted", async ({ page, request }) => {
    const preview = await request.post(`${API}/api/imports/preview?filename=synthetic_preview.csv`, {
      data: readFileSync(SAMPLE_PATH),
      headers: { "content-type": "text/csv" },
    });
    const { preview_id: id } = (await preview.json()) as { preview_id: string };
    const commit = await request.post(`${API}/api/imports/${id}/commit`, {
      data: { template_name: "E2E template" },
    });
    expect(commit.ok()).toBe(true);

    await openScreen(page, "Settings", "Settings");
    const templates = page.getByRole("region", { name: "Column templates" });
    await expect(templates.getByText("E2E template")).toBeVisible();

    await templates.getByRole("button", { name: "Rename E2E template" }).click();
    await templates.getByLabel("New name for E2E template").fill("Renamed template");
    await templates.getByRole("button", { name: "Save name" }).click();
    await expect(templates.getByText("Renamed template")).toBeVisible();

    await templates.getByRole("button", { name: "Delete Renamed template" }).click();
    await templates.getByRole("button", { name: "Confirm delete Renamed template" }).click();
    await expect(templates.getByText("No templates yet")).toBeVisible();
  });

  test("everything can be exported as one zip", async ({ page, request }) => {
    await importSample(request);
    await openScreen(page, "Settings", "Settings");
    const downloading = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download everything" }).click();
    const download = await downloading;
    expect(download.suggestedFilename()).toMatch(/^obsidian-ledger-export-\d{8}\.zip$/);
  });
});

test.describe("keyboard only", () => {
  async function goTo(page: Page, name: string, heading: string) {
    await page.goto("/");
    const button = page.getByRole("button", { name, exact: true });
    await tabTo(page, button);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }

  test("Analytics: reach the explorer and the selection form", async ({ page, request }) => {
    await importSample(request);
    await goTo(page, "Analytics", "Analytics");
    const dimension = page.getByLabel("Group trades by");
    await tabTo(page, dimension);
    await page.keyboard.press("ArrowDown");
    await expect(dimension).not.toHaveValue("symbol");
    await expect(page.getByRole("region", { name: "Segment explorer" }).locator("tbody tr").first()).toBeVisible();

    const atMost = page.getByLabel("Net P&L at most");
    await tabTo(page, atMost, 160);
    await page.keyboard.type("-1");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Open in the Trades table" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(".selection-note")).toBeVisible();
  });

  test("Behavior: the formula tooltip opens on focus and closes with Escape", async ({
    page,
    request,
  }) => {
    await importSample(request);
    await goTo(page, "Behavior", "Behavior");
    const tip = page.getByRole("button", { name: "How the Discipline Score is calculated" });
    await tabTo(page, tip);
    await expect(page.getByRole("tooltip")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);
  });

  test("Simulator: set a rule and read the result", async ({ page, request }) => {
    await importSample(request);
    await goTo(page, "Simulator", "Simulator");
    const cap = page.getByLabel("Most trades per day");
    await tabTo(page, cap);
    await page.keyboard.type("3");
    await expect(page.getByRole("region", { name: "Before and after table" })).toBeVisible();
    const hour = page.getByRole("checkbox", { name: "14", exact: true });
    await tabTo(page, hour, 120);
    await page.keyboard.press("Space");
    await expect(hour).toBeChecked();
    await expect(page.getByText(/excluded hour/)).toBeVisible();
  });

  test("Settings: the wipe stays locked until the phrase is typed", async ({ page, request }) => {
    await importSample(request);
    await goTo(page, "Settings", "Settings");
    const wipe = page.getByRole("button", { name: "Wipe everything" });
    await expect(wipe).toBeDisabled();
    const confirm = page.getByRole("textbox", { name: /to confirm/ });
    await tabTo(page, confirm, 160);
    await page.keyboard.type("delete all my");
    await expect(wipe).toBeDisabled();
    await page.keyboard.type(" data");
    await expect(wipe).toBeEnabled();
    await page.keyboard.press("Tab");
    await expect(wipe).toBeFocused();
  });
});
