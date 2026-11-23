import { expect, test } from "@playwright/test";

test("the glyph field follows the pointer and matches the reference at rest time", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      // The existing Zod JIT probe in the entry bundle falls back under CSP.
      if (event.blockedURI === "eval" && /\/assets\/index-[^/]+\.js$/.test(event.sourceFile)) return;
      document.documentElement.dataset.glyphCspViolation = event.violatedDirective;
    });
  });
  await page.goto("/");
  const canvas = page.locator(".wave-grid-layer canvas");
  await expect(canvas).toHaveAttribute("aria-hidden", "true");
  await expect(canvas).toHaveCSS("pointer-events", "none");
  await expect.poll(() => canvas.evaluate((element: HTMLCanvasElement) => {
    const pixels = element.getContext("2d")?.getImageData(0, 0, 52, 52).data ?? [];
    return pixels.some((value, index) => index % 4 === 3 && value > 4);
  })).toBe(true);
  const bounds = (await canvas.boundingBox())!;
  const pointer = { x: Math.round(bounds.x + bounds.width * 0.45), y: Math.round(bounds.y + 145) };
  await page.mouse.move(pointer.x, pointer.y);
  await expect.poll(() => canvas.evaluate((element: HTMLCanvasElement, position) => {
    const bounds = element.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio, 1.5);
    const x = (position.x - bounds.left) * dpr;
    const y = (position.y - bounds.top) * dpr;
    const context = element.getContext("2d")!;
    return context.getImageData(x - 20, y - 20, 40, 40).data.some((value, index) => index % 4 === 3 && value > 100);
  }, pointer)).toBe(true);

  const fidelity = await canvas.evaluate((element: HTMLCanvasElement, position) => {
    const bounds = element.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio, 1.5);
    const sx = position.x - bounds.left;
    const sy = position.y - bounds.top;
    const reference = document.createElement("canvas");
    reference.width = element.width;
    reference.height = element.height;
    const ctx = reference.getContext("2d")!;
    const style = getComputedStyle(document.documentElement);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = `400 15px ${style.getPropertyValue("--font-mono").trim()}`;
    ctx.fillStyle = style.getPropertyValue("--palette-white").trim();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let j = 0; j <= Math.ceil(bounds.height / 24); j++) {
      for (let i = 0; i <= Math.ceil(bounds.width / 24); i++) {
        const x = i * 24;
        const y = j * 24;
        const dx = x - sx;
        const dy = y - sy;
        const length = Math.hypot(dx, dy);
        const k = Math.exp(-2.2 * (dx * dx + dy * dy) / (190 * 190));
        const n = Math.sin(i * 0.31) + Math.cos(j * 0.27) + Math.sin((i + j) * 0.14)
          + k * 1.6 * Math.sin(i * 0.5 - j * 0.5);
        const index = ((Math.floor((n + 3.2) * 0.9) % 3) + 3) % 3;
        const push = k > 0.001 ? 5 * k / (length || 1) : 0;
        ctx.globalAlpha = Number((0.10 + 0.85 * k).toFixed(3));
        ctx.fillText(["+", "=", "*"][index]!, x + dx * push, y + dy * push);
      }
    }
    const expected = ctx.getImageData(0, 0, reference.width, reference.height).data;
    const actual = element.getContext("2d")!.getImageData(0, 0, reference.width, reference.height).data;
    let error = 0, near = 0, nearCount = 0, far = 0, farCount = 0;
    for (let i = 0; i < actual.length; i += 4) {
      const a = actual[i + 3]!;
      const e = expected[i + 3]!;
      for (let c = 0; c < 3; c++) error += Math.abs(actual[i + c]! * a - expected[i + c]! * e) / 255;
      error += Math.abs(a - e);
      const distance = Math.hypot(i / 4 % reference.width / dpr - sx, Math.floor(i / 4 / reference.width) / dpr - sy);
      if (distance < 100) { near += a; nearCount++; }
      if (distance > 320) { far += a; farCount++; }
    }
    return { error: error / actual.length / 255, near: near / nearCount, far: far / farCount };
  }, pointer);
  expect(fidelity.error).toBeLessThan(2 / 255);
  expect(fidelity.near).toBeGreaterThan(fidelity.far * 2);
  await page.evaluate(() => { document.documentElement.dataset.effects = "paused"; });
  await expect(canvas).toBeHidden();
  await page.evaluate(() => { delete document.documentElement.dataset.effects; });
  await expect(canvas).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-glyph-csp-violation");
  expect(errors).toEqual([]);
});

test("the glyph field is disabled on touch-only devices", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage();
    await page.goto(baseURL!);
    const canvas = page.locator(".wave-grid-layer canvas");
    await expect(canvas).toBeAttached();
    await expect(canvas).toBeHidden();
  } finally {
    await context.close();
  }
});
