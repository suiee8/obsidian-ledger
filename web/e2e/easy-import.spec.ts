import { resolve } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const template = resolve(process.cwd(), "public/templates/obsidian-ledger-template.csv");
const headerless = resolve(process.cwd(), "../samples/headerless_trades.csv");

async function openImport(page: Page) {
  await page.addInitScript(() => {
    const disable = () => { document.documentElement.dataset.shader = "off"; };
    if (document.documentElement) disable();
    else document.addEventListener("DOMContentLoaded", disable, { once: true });
    document.addEventListener("securitypolicyviolation", (event) => {
      document.documentElement.dataset.importCspViolation = event.violatedDirective;
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Import", exact: true }).click();
}

test("the template imports from the keyboard and Details can re-import it", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await openImport(page);
  const input = page.locator(".dropzone");
  await input.focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(template);
  const notice = page.locator(".import-status");
  await expect(notice).toContainText(/Imported [03] trades from obsidian-ledger-template\.csv/);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "One thing we need" })).toHaveCount(0);

  await notice.getByRole("button", { name: "Details" }).click();
  const details = page.getByRole("dialog", { name: "What we found" });
  await expect(details.getByRole("heading", { name: "Warnings" })).toHaveCount(0);
  await expect(details.getByRole("combobox")).toHaveCount(0);
  await details.getByRole("button", { name: "Edit mapping" }).click();
  await expect(details.getByRole("combobox", { name: "Role for symbol" })).toHaveValue("symbol");
  await details.getByRole("button", { name: "Re-import with these settings" }).click();
  await expect(details.getByRole("status")).toContainText("Added 0 new trades.");
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await expect(page.locator("html")).not.toHaveAttribute("data-import-csp-violation");
  expect(errors).toEqual([]);
});

test("an ambiguous headerless file asks one small question at a time", async ({ page }) => {
  await openImport(page);
  await page.getByLabel("Trade file", { exact: true }).setInputFiles(headerless);
  const question = page.locator("form").filter({ has: page.getByRole("heading", { name: "One thing we need" }) });
  await expect(question).toBeVisible();
  const dropdowns = question.getByRole("combobox");
  expect(await dropdowns.count()).toBeGreaterThan(0);
  expect(await dropdowns.count()).toBeLessThanOrEqual(3);
  await expect(question.getByRole("button", { name: "Continue" })).toBeEnabled();
});

test("a batch lands on the Dashboard after every file is saved", async ({ page }) => {
  await openImport(page);
  await page.getByLabel("Trade file", { exact: true }).setInputFiles(["first", "second"].map((id, i) => ({
    name: `${id}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from("trade_id,symbol,side,entry_time,exit_time,qty,net_pnl\n"
      + `${id},AAPL,long,2026-01-${10 + i}T10:00:00Z,2026-01-${10 + i}T11:00:00Z,5,10\n`),
  })));
  await expect(page.locator(".import-status")).toContainText("Imported 2 trades from 2 files.");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});

test("unsupported files and files we cannot mostly read link to the template", async ({ page }) => {
  await openImport(page);
  const input = page.getByLabel("Trade file", { exact: true });
  await input.setInputFiles({ name: "unsupported.pdf", mimeType: "application/pdf", buffer: Buffer.from("not a trade file") });
  await expect(page.getByRole("alert")).toContainText("We couldn't open");
  await expect(page.getByRole("link", { name: "Download template" }).last()).toHaveAttribute("href", /obsidian-ledger-template\.csv$/);
  await input.setInputFiles({ name: "bad-rows.csv", mimeType: "text/csv", buffer: Buffer.from(
    "trade_id,symbol,side,entry_time,exit_time,qty,net_pnl\n" +
    [1, 2, 3, 4].map((id) => `${id},AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,${id === 1 ? 5 : "bad"},10`).join("\n"),
  ) });
  await expect(page.getByRole("alert")).toContainText("We couldn't read most of this file");
  await expect(page.getByRole("link", { name: "Download template" }).last()).toBeVisible();
});

for (const width of [1440, 390]) {
  test(`the import screen and column guide pass axe at ${width}px`, async ({ page }) => {
    await openImport(page);
    await page.setViewportSize({ width, height: 900 });
    const audit = () => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect((await audit()).violations.map((issue) => issue.id)).toEqual([]);
    await page.getByRole("button", { name: "Column guide" }).click();
    await expect(page.getByRole("dialog", { name: "Column guide" })).toBeVisible();
    expect((await audit()).violations.map((issue) => issue.id)).toEqual([]);
  });
}
