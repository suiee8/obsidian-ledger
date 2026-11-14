import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { importSample } from "./helpers";

// Phase 6C: color balance, the Pause background toggle, the shader fallback, and the screenshots
// and video saved under docs/screens. This file sorts before the others so the throwaway test
// database only holds the 1,000-trade sample when it runs.

const OUT = resolve(process.cwd(), "..", "docs", "screens");
const MEXC_PATH = resolve(process.cwd(), "..", "samples", "mexc_futures_order_history_normalized.csv");

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

type Share = { blue: number; charcoal: number; white: number; other: number };

/** Decodes a screenshot inside the page with a canvas and sorts its pixels into color families. */
async function measure(page: Page, png: Buffer): Promise<Share> {
  return page.evaluate(async (base64) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("no 2d context");
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let blue = 0;
    let charcoal = 0;
    let white = 0;
    let other = 0;
    const total = data.length / 4;
    for (let index = 0; index < data.length; index += 4) {
      const r = (data[index] ?? 0) / 255;
      const g = (data[index + 1] ?? 0) / 255;
      const b = (data[index + 2] ?? 0) / 255;
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const lightness = (max + min) / 2;
      const delta = max - min;
      const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
      let hue = 0;
      if (delta !== 0) {
        if (max === r) hue = ((g - b) / delta) % 6;
        else if (max === g) hue = (b - r) / delta + 2;
        else hue = (r - g) / delta + 4;
        hue = (hue * 60 + 360) % 360;
      }
      const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      if (luminance > 0.8) white += 1;
      else if (hue >= 215 && hue <= 235 && saturation > 0.35) blue += 1;
      else if (saturation <= 0.35 && luminance < 0.3) charcoal += 1;
      else other += 1;
    }
    return { blue: blue / total, charcoal: charcoal / total, white: white / total, other: other / total };
  }, png.toString("base64"));
}

async function shaderOff(page: Page) {
  await page.addInitScript(() => {
    const mark = () => {
      document.documentElement.dataset.shader = "off";
    };
    if (document.documentElement) mark();
    else {
      new MutationObserver((_records, observer) => {
        if (document.documentElement) {
          mark();
          observer.disconnect();
        }
      }).observe(document, { childList: true });
    }
  });
}

async function stillShader(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await shaderOff(page);
}

async function openScreen(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).click();
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
}

const DASHBOARD_RANGE = { blue: [0.4, 0.5], charcoal: [0.4, 0.5], whiteMax: 0.1 } as const;
const ANALYSIS_RANGE = { blue: [0.25, 0.4], charcoal: [0.55, 0.7], whiteMax: 0.1 } as const;

const SCREENS: {
  id: string;
  range: { blue: readonly [number, number]; charcoal: readonly [number, number]; whiteMax: number };
  open: (page: Page) => Promise<void>;
}[] = [
  {
    id: "dashboard",
    range: DASHBOARD_RANGE,
    open: async (page) => {
      await expect(page.locator(".kpi").first()).toBeVisible();
    },
  },
  {
    id: "import",
    range: DASHBOARD_RANGE,
    open: async (page) => {
      await openScreen(page, "Import");
      await expect(page.locator(".dropzone")).toBeVisible();
    },
  },
  {
    id: "trades",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await openScreen(page, "Trades");
      await expect(page.getByRole("table", { name: "Trades" })).toBeVisible();
    },
  },
  {
    id: "analytics",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await openScreen(page, "Analytics");
      await expect(page.locator(".chart-scatter canvas").first()).toBeVisible();
    },
  },
  {
    id: "behavior",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await openScreen(page, "Behavior");
      await expect(page.getByRole("region", { name: "Overtrading timeline" }).locator("canvas")).toBeVisible();
    },
  },
  {
    id: "simulator",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await openScreen(page, "Simulator");
      await expect(page.getByLabel("Most trades per day")).toBeVisible();
    },
  },
  {
    id: "settings",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await openScreen(page, "Settings");
      await expect(page.getByRole("region", { name: "Wipe everything" })).toBeVisible();
    },
  },
  {
    id: "coach",
    range: ANALYSIS_RANGE,
    open: async (page) => {
      await page.getByRole("button", { name: "Coach", exact: true }).click();
      await expect(page.getByRole("complementary", { name: "Coach" })).toBeVisible();
    },
  },
];

test("above-the-fold color balance at 1440x900 with the shader off", async ({ page, request }) => {
  await importSample(request);
  await stillShader(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const report: Record<string, Share> = {};
  for (const screen of SCREENS) {
    await screen.open(page);
    await settle(page);
    const png = await page.screenshot({ path: resolve(OUT, `balance-${screen.id}-1440.png`) });
    report[screen.id] = await measure(page, png);
  }
  writeFileSync(resolve(OUT, "color-balance.json"), JSON.stringify(report, null, 2));
  const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
  for (const screen of SCREENS) {
    const share = report[screen.id];
    if (!share) continue;
    console.log(
      `[balance] ${screen.id}: blue ${percent(share.blue)}, charcoal ${percent(share.charcoal)}, white ${percent(share.white)}, other ${percent(share.other)}`,
    );
  }
  for (const screen of SCREENS) {
    const share = report[screen.id];
    expect(share, screen.id).toBeDefined();
    if (!share) continue;
    expect(share.blue, `${screen.id} blue`).toBeGreaterThanOrEqual(screen.range.blue[0]);
    expect(share.blue, `${screen.id} blue`).toBeLessThanOrEqual(screen.range.blue[1]);
    expect(share.charcoal, `${screen.id} charcoal`).toBeGreaterThanOrEqual(screen.range.charcoal[0]);
    expect(share.charcoal, `${screen.id} charcoal`).toBeLessThanOrEqual(screen.range.charcoal[1]);
    expect(share.white, `${screen.id} white`).toBeLessThanOrEqual(screen.range.whiteMax);
  }
});

test.describe("Pause background", () => {
  test("pauses the shader, persists after a reload, and can be resumed", async ({ page }) => {
    await page.goto("/");
    const toggle = page.getByRole("button", { name: "Pause background" });
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator(".aurora-layer")).toHaveAttribute("data-background", "on");

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".aurora-layer")).toHaveAttribute("data-background", "paused");
    await expect(page.locator(".aurora-layer")).toHaveAttribute("data-render-state", /^(static|fallback)$/);

    await page.reload();
    await expect(page.getByRole("button", { name: "Pause background" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".aurora-layer")).toHaveAttribute("data-background", "paused");

    await page.getByRole("button", { name: "Pause background" }).click();
    await expect(page.getByRole("button", { name: "Pause background" })).toHaveAttribute("aria-pressed", "false");
  });

  test("is also in the command palette", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+k");
    await page.getByRole("option", { name: "Pause background" }).click();
    await expect(page.getByRole("button", { name: "Pause background" })).toHaveAttribute("aria-pressed", "true");
  });

  test("starts paused when the OS asks for reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Pause background" })).toHaveAttribute("aria-pressed", "true");
  });
});

test("the CSS fallback shows when the shader is off and follows the palette", async ({ page }) => {
  await shaderOff(page);
  await page.goto("/");
  const layer = page.locator(".aurora-layer");
  await expect(layer).toHaveAttribute("data-fallback", "true");
  await expect(layer).toHaveAttribute("data-render-state", "fallback");
  await expect(page.locator(".aurora-canvas")).toHaveCSS("opacity", "0");
  const wash = await page.evaluate(() => getComputedStyle(document.querySelector(".aurora-layer") as Element, "::before").backgroundImage);
  expect(wash).toContain("radial-gradient");
});

const SHOTS = [
  { id: "import", open: async (page: Page) => {
      await openScreen(page, "Import");
      await page.locator('input[type="file"]').setInputFiles(MEXC_PATH);
      await expect(page.locator(".import-preview")).toBeVisible();
    } },
  { id: "dashboard", open: async (page: Page) => {
      await openScreen(page, "Dashboard");
      await expect(page.locator(".kpi").first()).toBeVisible();
    } },
  { id: "trades", open: async (page: Page) => {
      await openScreen(page, "Trades");
      await expect(page.getByRole("table", { name: "Trades" })).toBeVisible();
    } },
  { id: "settings", open: async (page: Page) => {
      await openScreen(page, "Settings");
      await expect(page.getByRole("region", { name: "Wipe everything" })).toBeVisible();
    } },
  { id: "coach", open: async (page: Page) => {
      await openScreen(page, "Dashboard");
      await page.getByRole("button", { name: "Coach", exact: true }).click();
      await expect(page.getByRole("complementary", { name: "Coach" })).toBeVisible();
    } },
];

for (const width of [1440, 1024, 390]) {
  for (const shader of ["off", "on"] as const) {
    test(`screenshots at ${width} px with the shader ${shader}`, async ({ page, request }) => {
      await importSample(request);
      if (shader === "off") await stillShader(page);
      await page.setViewportSize({ width, height: width >= 1024 ? 900 : 844 });
      await page.goto("/");
      for (const shot of SHOTS) {
        await shot.open(page);
        await settle(page);
        await page.screenshot({ path: resolve(OUT, `${shot.id}-${width}-shader-${shader}.png`) });
        if (shot.id === "coach") await page.getByRole("button", { name: "Coach", exact: true }).click();
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, "no horizontal page scroll").toBeLessThanOrEqual(0);
    });
  }
}

test("records the Dashboard and Import with the shader on", async ({ browser, request }) => {
  await importSample(request);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: resolve(OUT, "video-tmp"), size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.locator(".kpi").first()).toBeVisible();
  await page.waitForTimeout(4000);
  await openScreen(page, "Import");
  await expect(page.locator(".dropzone")).toBeVisible();
  await page.waitForTimeout(4000);
  const video = page.video();
  await context.close();
  await video?.saveAs(resolve(OUT, "motion-on.webm"));
  await video?.delete();
});
