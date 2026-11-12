import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { palette } from "./tokens";

const here = dirname(fileURLToPath(import.meta.url));

describe("palette", () => {
  it("matches the Obsidian and Sapphire spec", () => {
    expect(palette.background).toBe("#0B0D11");
    expect(palette.surface1).toBe("#11141A");
    expect(palette.surface2).toBe("#171B23");
    expect(palette.surface3).toBe("#1E232D");
    expect(palette.border).toBe("#262C38");
    expect(palette.borderSubtle).toBe("#1D222C");
    expect(palette.ink).toBe("#E8ECF4");
    expect(palette.muted).toBe("#9AA4B8");
    expect(palette.dim).toBe("#6B7488");
    expect(palette.royal500).toBe("#4169E1");
    expect(palette.royal400).toBe("#6384EE");
    expect(palette.royal300).toBe("#94ADF6");
    expect(palette.royal600).toBe("#3454C0");
    expect(palette.royal700).toBe("#27409A");
    expect(palette.ice).toBe("#C9D6FF");
    expect(palette.profit).toBe("#3DDC97");
    expect(palette.loss).toBe("#FF5C6C");
    expect(palette.warning).toBe("#6384EE");
  });

  it("is written into the stylesheet", () => {
    const css = readFileSync(resolve(here, "index.css"), "utf8").toLowerCase();
    for (const hex of Object.values(palette)) {
      expect(css).toContain(hex.toLowerCase());
    }
    expect(css).toContain("rgba(65,105,225,0.35)");
  });
});
