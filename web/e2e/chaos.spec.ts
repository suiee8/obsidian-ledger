import { expect, test, type Page } from "@playwright/test";

import { importSample } from "./helpers";

const API_PATTERN = "http://127.0.0.1:8000/**";

/** Unhandled page errors fail the test. Browser-logged network failures from deliberately aborted
 *  requests are expected, so only uncaught exceptions and rejections count. */
function trackPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

const badge = (page: Page) => page.locator(".health-badge");

test.beforeEach(async ({ request }) => {
  await importSample(request);
});

test("killing the API shows Offline, keeps the last data on screen, and recovers", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");
  await expect(page.locator(".kpi-strip")).toBeVisible();
  await expect(badge(page)).toContainText("online");

  await page.route(API_PATTERN, (route) => route.abort("connectionrefused"));
  // Refocusing and rechecking is how a user notices. Clicking the badge probes the API.
  await badge(page).click();
  await expect(badge(page)).toContainText("offline");
  await expect(badge(page)).toHaveAttribute("aria-label", /displayed data may be stale/);
  await expect(page.locator(".kpi-strip")).toBeVisible();

  await page.unroute(API_PATTERN);
  await badge(page).click();
  await expect(badge(page)).toContainText("online", { timeout: 15_000 });
  expect(errors).toEqual([]);
});

test("stalled API calls time out into Offline instead of hanging the screen", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");
  await expect(page.locator(".kpi-strip")).toBeVisible();

  await page.route(/\/health(\/ready)?$/, async (route) => {
    // Never answer: the 5 s probe timeout has to end this.
    await new Promise((resolve) => setTimeout(resolve, 8_000));
    await route.abort("timedout").catch(() => undefined);
  });
  await badge(page).click();
  await expect(badge(page)).toContainText("offline", { timeout: 10_000 });
  await expect(page.locator(".kpi-strip")).toBeVisible();

  await page.unroute(/\/health(\/ready)?$/);
  await badge(page).click();
  await expect(badge(page)).toContainText("online", { timeout: 15_000 });
  expect(errors).toEqual([]);
});

test("a degraded readiness check shows Degraded, not Offline", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.route("**/health/ready", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "degraded", checks: { ai: "unavailable" } }),
    }),
  );
  await page.goto("/");
  await expect(badge(page)).toContainText("degraded");
  await expect(badge(page)).toHaveAttribute("aria-label", "Local API degraded");

  await page.unroute("**/health/ready");
  await badge(page).click();
  await expect(badge(page)).toContainText("online");
  expect(errors).toEqual([]);
});

test("an unreachable AI model shows AI unavailable while the app stays usable", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.route("**/health/ready", async (route) => {
    const upstream = await route.fetch();
    const body = (await upstream.json()) as { checks: Record<string, string> };
    body.checks.ai = "unavailable";
    await route.fulfill({ response: upstream, json: { ...body, status: "ready" } });
  });
  await page.goto("/");
  await expect(badge(page)).toContainText("AI unavailable");
  await expect(page.locator(".kpi-strip")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a different API version shows a mismatch warning", async ({ page }) => {
  await page.route("**/health", async (route) => {
    const upstream = await route.fetch();
    const body = (await upstream.json()) as Record<string, unknown>;
    await route.fulfill({ response: upstream, json: { ...body, version: "99.0.0" } });
  });
  await page.goto("/");
  await expect(badge(page)).toContainText("version mismatch");
});

test("a dropped Coach stream reports an error and a rerun recovers", async ({ page }) => {
  const errors = trackPageErrors(page);
  await page.goto("/");
  await expect(page.locator(".kpi-strip")).toBeVisible();

  await page.route("**/api/coach/stream**", (route) => route.abort("connectionreset"));
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await expect(page.getByText(/could not reach the local API/i).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.unroute("**/api/coach/stream**");
  await page.getByRole("button", { name: /run again|try again|rerun/i }).first().click();
  await expect(page.getByText(/could not reach the local API/i)).toHaveCount(0, { timeout: 30_000 });
  expect(errors).toEqual([]);
});
