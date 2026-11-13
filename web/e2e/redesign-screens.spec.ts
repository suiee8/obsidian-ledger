import { mkdirSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

import { expect, test } from "@playwright/test";

import { importSample } from "./helpers";

const OUT = resolve(process.cwd(), "..", "docs", "screens");
const WIDTHS = [1440, 1024, 390];
const BASELINE_CSS_GZIP_BYTES = 36_351;
const CSS_GROWTH_BUDGET_BYTES = 20 * 1024;

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.documentElement.dataset.shader = "off";
  });
});

for (const width of WIDTHS) {
  test.describe(`redesigned screens at ${width} px`, () => {
    test.use({ viewport: { width, height: width >= 1024 ? 1000 : 844 } });

    test("analytics, behavior, simulator, settings, and samples", async ({ page, request }) => {
      await importSample(request);
      await page.goto("/");

      await page.getByRole("button", { name: "Analytics", exact: true }).click();
      await expect(page.locator(".chart-scatter canvas").first()).toBeVisible();
      await page.screenshot({ path: `${OUT}/analytics-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Behavior", exact: true }).click();
      await expect(page.getByRole("region", { name: "Overtrading timeline" }).locator("canvas")).toBeVisible();
      await page.screenshot({ path: `${OUT}/behavior-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Simulator", exact: true }).click();
      await page.getByLabel("Most trades per day").fill("3");
      await expect(page.getByRole("region", { name: "Before and after table" })).toBeVisible();
      await page.screenshot({ path: `${OUT}/simulator-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Settings", exact: true }).click();
      await expect(page.getByRole("region", { name: "Wipe everything" })).toBeVisible();
      await page.screenshot({ path: `${OUT}/settings-${width}.png`, fullPage: true });

      await page.getByRole("button", { name: "Sample files", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Fixture catalog" })).toBeVisible();
      await page.screenshot({ path: `${OUT}/samples-${width}.png`, fullPage: true });
    });
  });
}

test("a trade filter updates the visible chip in under 100ms", async ({ page, request }) => {
  await importSample(request);
  await page.goto("/");
  await page.getByRole("button", { name: "Trades", exact: true }).click();

  const select = page.getByLabel("Add symbol filter");
  await expect(select).toBeVisible();
  await expect.poll(() => select.locator("option").count()).toBeGreaterThan(1);
  const symbol = await select.locator("option").nth(1).getAttribute("value");
  if (!symbol) throw new Error("The sample import did not provide a symbol filter option");

  const updateTime = page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const filterBar = document.querySelector(".filter-bar");
        const symbolFilter = document.querySelector<HTMLSelectElement>('[aria-label="Add symbol filter"]');
        if (!filterBar || !symbolFilter) throw new Error("The trade filter is not mounted");

        const initialChips = filterBar.querySelectorAll(".chip-button").length;
        let startedAt = 0;
        const observer = new MutationObserver(() => {
          if (startedAt && filterBar.querySelectorAll(".chip-button").length > initialChips) {
            observer.disconnect();
            requestAnimationFrame(() => resolve(performance.now() - startedAt));
          }
        });
        observer.observe(filterBar, { childList: true, subtree: true });
        symbolFilter.addEventListener("change", () => {
          startedAt = performance.now();
        }, { once: true });
      }),
  );
  await select.selectOption(symbol);
  const elapsed = await updateTime;
  expect(elapsed, `The filter chip appeared after ${elapsed.toFixed(1)} ms`).toBeLessThan(100);
});

test("the populated dashboard defers chart JavaScript until after its first paint", async ({ page, request }) => {
  const assetsDirectory = resolve(process.cwd(), "dist", "assets");
  const assets = readdirSync(assetsDirectory);
  const cssFiles = assets.filter((name) => name.endsWith(".css"));
  const shaderFile = assets.find((name) => name.startsWith("SapphireAurora-") && name.endsWith(".js"));
  if (cssFiles.length === 0) throw new Error("The production build contains no CSS assets");
  if (!shaderFile) throw new Error("The production build contains no Sapphire Aurora chunk");

  const cssGzipBytes = cssFiles.reduce(
    (total, name) => total + gzipSync(readFileSync(resolve(assetsDirectory, name))).byteLength,
    0,
  );
  const shaderGzipBytes = gzipSync(readFileSync(resolve(assetsDirectory, shaderFile))).byteLength;
  console.log(`Production CSS: ${cssGzipBytes} bytes gzip; Sapphire Aurora: ${shaderGzipBytes} bytes gzip`);
  expect(cssGzipBytes).toBeLessThanOrEqual(BASELINE_CSS_GZIP_BYTES + CSS_GROWTH_BUDGET_BYTES);
  expect(shaderGzipBytes).toBeLessThanOrEqual(15 * 1024);

  await importSample(request);
  let releaseDashboard!: () => void;
  const dashboardGate = new Promise<void>((resolveGate) => {
    releaseDashboard = resolveGate;
  });
  await page.route("**/api/dashboard**", async (route) => {
    const response = await route.fetch();
    await dashboardGate;
    await route.fulfill({ response });
  });

  const scripts = new Map<string, Promise<Buffer>>();
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.endsWith(".js")) {
      scripts.set(url.href, response.body().then((body) => Buffer.from(body)));
    }
  });

  try {
    await page.goto("/");
    await expect(page.getByLabel("Loading dashboard")).toBeVisible();
    await page.evaluate(
      () => new Promise<void>((resolvePaint) => requestAnimationFrame(() => requestAnimationFrame(() => resolvePaint()))),
    );

    const initialUrls = await page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .filter((entry) => entry.name.endsWith(".js"))
        .map((entry) => entry.name),
    );
    const initialBodies = await Promise.all(
      initialUrls.map((url) => {
        const body = scripts.get(url);
        if (!body) throw new Error(`Missing captured JavaScript response for ${url}`);
        return body;
      }),
    );
    const gzipBytes = initialBodies.reduce((total, body) => total + gzipSync(body).byteLength, 0);
    console.log(`Populated Dashboard first-paint JavaScript: ${gzipBytes} bytes gzip`);
    expect(gzipBytes).toBeLessThan(250 * 1024);
    expect(initialUrls.some((url) => /useChart-[^/]+\.js$/.test(new URL(url).pathname))).toBe(false);

    releaseDashboard();
    await expect(page.getByRole("region", { name: "Headline numbers" })).toBeVisible();
    await expect(page.locator(".chart-equity canvas")).toBeVisible();
  } finally {
    releaseDashboard();
  }
});
