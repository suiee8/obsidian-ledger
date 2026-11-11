import { expect, test } from "@playwright/test";

import { importSample } from "./helpers";

test("the rail, command palette, and trade drawer work from the keyboard alone", async ({
  page,
  request,
}) => {
  await importSample(request);
  await page.goto("/");
  await expect(page.locator(".kpi-strip")).toBeVisible();

  // Reach the Trades rail button with Tab, then activate it with Enter.
  const trades = page.getByRole("button", { name: "Trades", exact: true });
  for (let step = 0; step < 40; step += 1) {
    if (await trades.evaluate((element) => element === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(trades).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Trades", exact: true })).toBeVisible();

  // Ctrl+K opens the command palette, and Escape closes it.
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // A trade row opens the drawer with Enter, and Escape closes it.
  const firstRow = page.locator('[role="row"][aria-rowindex="1"]');
  await firstRow.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: /Trade/ });
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});
