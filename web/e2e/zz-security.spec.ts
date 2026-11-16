import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, request as playwrightRequest, test } from "@playwright/test";

import { API } from "./helpers";

const PAYLOAD = "<img src=x onerror=window.__xss=1>";
const IBKR = resolve(process.cwd(), "..", "samples", "ibkr_executions.csv");

test("hostile file contents render as text and never run script", async ({ page, request }) => {
  const hostile = readFileSync(IBKR, "utf8").replaceAll("AAPL", PAYLOAD);
  const preview = await request.post(`${API}/api/imports/preview?filename=hostile.csv`, {
    data: Buffer.from(hostile),
    headers: { "content-type": "text/csv" },
  });
  expect(preview.status()).toBeLessThan(500);
  if (preview.ok()) {
    const { preview_id: id } = (await preview.json()) as { preview_id: string };
    const commit = await request.post(`${API}/api/imports/${id}/commit`, { data: {} });
    expect(commit.status()).toBeLessThan(500);
  }

  const violations: string[] = [];
  page.on("pageerror", (error) => violations.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Trades", exact: true }).click();
  await page.waitForTimeout(1500);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  expect(await page.locator("img[src='x']").count()).toBe(0);
  expect(violations).toEqual([]);
});

test("the web app sends the client header on every API call", async ({ page }) => {
  const missing: string[] = [];
  page.on("request", (req) => {
    if (req.url().startsWith(API) && req.headers()["x-ledger-client"] !== "web") {
      missing.push(req.url());
    }
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.waitForTimeout(1000);
  expect(missing).toEqual([]);
});

test("the page is served with strict security headers", async ({ page }) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  const csp = headers["content-security-policy"] ?? "";
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toMatch(/script-src[^;]*unsafe-(inline|eval)/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
});

test("a request without the client header cannot write", async () => {
  const bare = await playwrightRequest.newContext({ extraHTTPHeaders: {} });
  const response = await bare.post(`${API}/api/wipe`, { data: { confirm: "no" } });
  expect(response.status()).toBe(403);
  await bare.dispose();
});

test("a forged origin is refused", async () => {
  const forged = await playwrightRequest.newContext({
    extraHTTPHeaders: { Origin: "http://evil.example", "X-Ledger-Client": "web" },
  });
  expect((await forged.get(`${API}/api/trades`)).status()).toBe(403);
  await forged.dispose();
});
