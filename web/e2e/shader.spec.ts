import { expect, test, type Page } from "@playwright/test";

import { importSample } from "./helpers";

const aurora = (page: Page) => page.locator(".aurora-layer");
const orb = (page: Page) => page.locator(".agent-presence");

test("the shader canvas is present but hidden from assistive technology", async ({ page }) => {
  await page.goto("/");
  const canvas = page.locator(".aurora-canvas");
  await expect(canvas).toBeAttached();
  await expect(canvas).toHaveAttribute("aria-hidden", "true");
  await expect(aurora(page)).toHaveAttribute("data-render-state", /^(animated|static|fallback)$/);
});

test("reduced motion keeps the shader static", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(aurora(page)).toHaveAttribute("data-render-state", /^(static|fallback)$/);
});

test("keeps cumulative layout shift below 0.05", async ({ page }) => {
  await page.addInitScript(() => {
    let total = 0;
    Object.defineProperty(window, "__ledgerLayoutShift", { get: () => total });
    const observer = new PerformanceObserver((entries) => {
      for (const entry of entries.getEntries()) {
        const shift = entry as PerformanceEntry & { value: number; hadRecentInput: boolean };
        if (!shift.hadRecentInput) total += shift.value;
      }
    });
    observer.observe({ type: "layout-shift", buffered: true });
  });
  await page.goto("/");
  await expect(orb(page)).toBeVisible();
  await page.waitForTimeout(1200);
  const layoutShift = await page.evaluate(
    () => (window as Window & { __ledgerLayoutShift?: number }).__ledgerLayoutShift ?? 0,
  );
  expect(layoutShift).toBeLessThan(0.05);
});

test("a missing WebGL2 context uses the CSS fallback", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      configurable: true,
      value: new Proxy(original, {
        apply(target, thisArg, args) {
          if (args[0] === "webgl2") return null;
          return Reflect.apply(target, thisArg, args);
        },
      }),
    });
  });
  await page.goto("/");
  await expect(aurora(page)).toHaveAttribute("data-fallback", "true");
  await expect(aurora(page)).toHaveAttribute("data-render-state", "fallback");
});

test("the shader pauses in a hidden tab and resumes when visible", async ({ page }) => {
  await page.goto("/");
  const layer = aurora(page);
  await expect(layer).toHaveAttribute("data-render-state", "animated");

  const setHidden = (hidden: boolean) =>
    page.evaluate((isHidden) => {
      Object.defineProperty(document, "hidden", { configurable: true, value: isHidden });
      document.dispatchEvent(new Event("visibilitychange"));
    }, hidden);

  await setHidden(true);
  await expect(layer).toHaveAttribute("data-paused", "true");
  await setHidden(false);
  await expect(layer).toHaveAttribute("data-paused", "false");
});

test("the presence orb reflects idle, thinking, error, and offline states", async ({ page, request }) => {
  await page.goto("/");
  await expect(orb(page)).toHaveAttribute("data-state", "idle");

  await importSample(request);
  await page.route("**/api/coach/stream**", () => undefined);
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await expect(orb(page)).toHaveAttribute("data-state", "thinking");

  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await page.unroute("**/api/coach/stream**");
  await page.route("**/api/coach/stream**", (route) => route.abort());
  await page.getByRole("button", { name: "Coach", exact: true }).click();
  await expect(orb(page)).toHaveAttribute("data-state", "error");

  await page.unroute("**/api/coach/stream**");
  await page.route("**/health", (route) => route.abort());
  await page.reload();
  await expect(orb(page)).toHaveAttribute("data-state", "offline");
});
