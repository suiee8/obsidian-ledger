import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { palette } from "../tokens";
import { cappedWhite, WHITE_CAP } from "./white";

const here = dirname(fileURLToPath(import.meta.url));

function luminance(hex: string): number {
  const channel = (offset: number) => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

describe("shader white highlights", () => {
  it("never add more than the cap as a share of final luminance", () => {
    for (let base = 0; base <= 1; base += 0.01) {
      for (const wanted of [0, 0.1, 0.5, 1]) {
        const white = cappedWhite(base, wanted);
        const share = white + base === 0 ? 0 : white / (base + white);
        expect(share).toBeLessThanOrEqual(WHITE_CAP + 1e-9);
      }
    }
  });

  it("uses the same formula in the fragment shader", () => {
    const glsl = readFileSync(resolve(here, "fragment.glsl"), "utf8");
    expect(glsl).toContain("uniform vec3 uWhite;");
    expect(glsl).toContain("uniform float uWhiteCap;");
    expect(glsl).toContain("uWhiteCap / (1.0 - uWhiteCap) * baseLuminance");
  });
});

describe("text on royal blue", () => {
  it("passes 4.5:1 for white on every blue the text can sit on", () => {
    expect(contrast(palette.white, palette.royal500)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(palette.white, palette.royal600)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(palette.white, palette.royal700)).toBeGreaterThanOrEqual(4.5);
  });

  it("is why the light text token is not used on blue", () => {
    expect(contrast(palette.ink, palette.royal500)).toBeLessThan(4.5);
  });
});
