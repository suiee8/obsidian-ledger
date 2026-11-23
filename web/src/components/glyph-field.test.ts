// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { easing, glyphIndex, influence, isPaused, readGlyphStyle } from "./glyph-field";

describe("glyph field", () => {
  it("matches the reference wave at fixed times and proximity values", () => {
    expect(glyphIndex(0, 0, 0)).toBe(0);
    expect(glyphIndex(3, 0, 1.25)).toBe(2);
    expect(glyphIndex(3, 0, 1.25, 0.8)).toBe(0);
  });

  it("falls off with distance", () => {
    expect(influence(0)).toBe(1);
    expect(influence(190 ** 2)).toBeCloseTo(Math.exp(-2.2));
    expect(influence(280 ** 2)).toBeLessThan(0.01);
  });

  it("eases equally over the same elapsed time", () => {
    const remaining = (hz: number) => (1 - easing(1000 / hz)) ** hz;
    expect(remaining(120)).toBeCloseTo(remaining(60), 12);
    expect(remaining(144)).toBeCloseTo(remaining(60), 12);
  });

  it("reads the theme's white and mono tokens each time", () => {
    const root = document.createElement("div");
    document.body.append(root);
    root.style.setProperty("--palette-white", "white");
    root.style.setProperty("--font-mono", "monospace");
    expect(readGlyphStyle(root)).toEqual({ color: "white", font: "400 15px monospace" });
    root.style.setProperty("--palette-white", "ivory");
    expect(readGlyphStyle(root).color).toBe("ivory");
    root.remove();
  });

  it("pauses on any of the four suspension conditions", () => {
    expect(isPaused(false, true, true, false)).toBe(false);
    expect(isPaused(true, true, true, false)).toBe(true);
    expect(isPaused(false, false, true, false)).toBe(true);
    expect(isPaused(false, true, false, false)).toBe(true);
    expect(isPaused(false, true, true, true)).toBe(true);
  });
});
