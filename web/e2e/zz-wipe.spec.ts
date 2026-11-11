import { expect, test } from "@playwright/test";

import { API, importSample } from "./helpers";

// This spec deletes all data from the test database, so it runs last (Playwright runs files in
// name order). The database is a throwaway folder made for this run, never your real data.

test("wipe needs the typed phrase, then removes every trade and file", async ({ page, request }) => {
  await importSample(request);
  const before = (await (await request.get(`${API}/api/settings`)).json()) as {
    data: { trades: number };
  };
  expect(before.data.trades).toBeGreaterThan(0);

  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const panel = page.getByRole("region", { name: "Wipe everything" });
  const button = panel.getByRole("button", { name: "Wipe everything" });
  const input = panel.getByRole("textbox", { name: /to confirm/ });

  await expect(button).toBeDisabled();
  await input.fill("delete everything");
  await expect(button).toBeDisabled();
  await input.fill("Delete all my data"); // wrong case
  await expect(button).toBeDisabled();
  await input.fill("delete all my data");
  await expect(button).toBeEnabled();
  await button.click();

  await expect(panel.getByRole("status")).toContainText("Everything was deleted");
  const after = (await (await request.get(`${API}/api/settings`)).json()) as {
    data: { trades: number; imports: number };
  };
  expect(after.data).toMatchObject({ trades: 0, imports: 0 });

  // The rest of the app shows its empty state.
  await page.getByRole("button", { name: "Dashboard", exact: true }).click();
  await expect(page.getByText("Import a journal to see your edge.")).toBeVisible();
});

test("the server refuses a wipe without the exact phrase", async ({ request }) => {
  const refused = await request.post(`${API}/api/wipe`, { data: { confirm: "yes" } });
  expect(refused.status()).toBe(422);
});
