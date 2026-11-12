import { describe, expect, it } from "vitest";

import { readChartPalette } from "./theme";

describe("chart palette accessibility behavior", () => {
  it("keeps the original color-blind profit and loss colors", () => {
    const palette = readChartPalette(true);

    expect(palette.profit).toBe("#4169E1");
    expect(palette.loss).toBe("#F5B84B");
  });
});
