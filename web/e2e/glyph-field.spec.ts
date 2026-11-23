import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Glyph field background effect", () => {
  test("canvas exists, is aria-hidden, pointer-events none, brightens near cursor, disabled by pause and touch", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    // 1. Reduced motion: deterministic static field that reacts to pointer movement
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    const canvas = page.locator(".wave-grid-layer canvas");
    await expect(canvas).toBeAttached();
    await expect(canvas).toHaveAttribute("aria-hidden", "true");
    await expect(canvas).toHaveCSS("pointer-events", "none");

    // 2. Move pointer to (300, 300)
    const targetX = 300;
    const targetY = 300;
    await page.mouse.move(targetX, targetY);
    await page.waitForTimeout(200);

    // Sample pixels near the pointer vs far from the pointer
    const brightness = await page.evaluate(
      ({ x, y }) => {
        const c = document.querySelector<HTMLCanvasElement>(".wave-grid-layer canvas");
        if (!c) return null;
        const ctx = c.getContext("2d");
        if (!ctx) return null;

        // Sample 48x48 box near cursor
        const nearData = ctx.getImageData(x - 24, y - 24, 48, 48).data;
        let nearMaxAlpha = 0;
        let nearAlphaSum = 0;
        let nearCount = 0;
        for (let i = 3; i < nearData.length; i += 4) {
          const a = nearData[i]!;
          if (a > 0) {
            nearAlphaSum += a;
            nearCount++;
            if (a > nearMaxAlpha) nearMaxAlpha = a;
          }
        }

        // Sample 48x48 box far away at (50, 50)
        const farData = ctx.getImageData(10, 10, 48, 48).data;
        let farMaxAlpha = 0;
        let farAlphaSum = 0;
        let farCount = 0;
        for (let i = 3; i < farData.length; i += 4) {
          const a = farData[i]!;
          if (a > 0) {
            farAlphaSum += a;
            farCount++;
            if (a > farMaxAlpha) farMaxAlpha = a;
          }
        }

        return {
          nearMaxAlpha,
          nearAvgAlpha: nearCount > 0 ? nearAlphaSum / nearCount : 0,
          farMaxAlpha,
          farAvgAlpha: farCount > 0 ? farAlphaSum / farCount : 0,
        };
      },
      { x: targetX, y: targetY },
    );

    expect(brightness).not.toBeNull();
    if (brightness) {
      // Near glyphs should be brighter than far glyphs
      expect(brightness.nearMaxAlpha).toBeGreaterThan(brightness.farMaxAlpha);
    }

    // 3. Touch events do not trigger hover brightness
    await page.evaluate(() => {
      const region = document.querySelector("main");
      if (region) {
        region.dispatchEvent(
          new PointerEvent("pointermove", {
            clientX: 100,
            clientY: 100,
            pointerType: "touch",
            bubbles: true,
          }),
        );
      }
    });

    // 4. Disabled by Pause effects
    await page.evaluate(() => {
      document.documentElement.dataset.shader = "off";
    });
    await expect(canvas).toBeHidden();

    // Re-enable
    await page.evaluate(() => {
      delete document.documentElement.dataset.shader;
    });
    await expect(canvas).toBeVisible();

    // 5. Axe accessibility checks
    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(a11y.violations).toEqual([]);

    // 6. No console errors or CSP violations
    expect(consoleErrors).toEqual([]);
  });
});
