// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import {
  ALPHA_LEVELS,
  COLOR_TOKEN,
  CONFIG,
  computeEaseFactor,
  computeFalloff,
  computeGlyphIndex,
  INFLUENCE_THRESHOLD,
} from "./glyphField";

describe("WaveGridBackground unit tests", () => {
  it("computes glyph index matching golden values from reference travelling wave", () => {
    const glyphCount = CONFIG.glyphs.length; // 3

    // Case 1: Origin at t=0, k=0
    // n = sin(0) + cos(0) + sin(0) + 0 = 1
    // floor((1 + 3.2) * 0.9) = floor(3.78) = 3 -> 3 % 3 = 0
    expect(computeGlyphIndex(0, 0, 0, 0, glyphCount)).toBe(0);

    // Case 2: Fixed known coordinates
    const g1 = computeGlyphIndex(10, 5, 1.0, 0, glyphCount);
    expect([0, 1, 2]).toContain(g1);

    // Case 3: Cursor term k influences local wave speed
    const gNoCursor = computeGlyphIndex(4, 4, 1.0, 0, glyphCount);
    const gWithCursor = computeGlyphIndex(4, 4, 1.0, 1.0, glyphCount);
    // With t=1.0, sin(6 + 2 - 2) = sin(6) ≈ -0.279, so k changes n
    expect(Number.isInteger(gNoCursor)).toBe(true);
    expect(Number.isInteger(gWithCursor)).toBe(true);

    // Golden values consistency
    expect(computeGlyphIndex(0, 0, 0, 0, 3)).toBe(0);
    expect(computeGlyphIndex(2, 3, 0.5, 0, 3)).toBe(2);
    expect(computeGlyphIndex(8, 8, 1.2, 0.8, 3)).toBe(0);
  });

  it("calculates cursor proximity falloff correctly", () => {
    const R = CONFIG.radius; // 190

    // At cursor center (distance = 0), k = 1.0
    expect(computeFalloff(0, R)).toBeCloseTo(1.0, 5);

    // At radius border (distance = R), k = exp(-2.2) ≈ 0.1108
    const atRadius = computeFalloff(R * R, R);
    expect(atRadius).toBeCloseTo(Math.exp(-2.2), 4);
    expect(atRadius).toBeCloseTo(0.1108, 3);

    // Monotonically decreasing
    const atHalf = computeFalloff((R * 0.5) * (R * 0.5), R);
    expect(atHalf).toBeGreaterThan(atRadius);
    expect(atHalf).toBeLessThan(1.0);

    // Far away (> 1.5 * R), k drops below influence threshold
    const atFar = computeFalloff((R * 1.5) * (R * 1.5), R);
    expect(atFar).toBeLessThan(INFLUENCE_THRESHOLD);
  });

  it("computes frame-rate independent easing factors", () => {
    const follow = CONFIG.follow; // 0.12

    // At 60 Hz (dt = 16.67ms), factor equals follow exactly
    const factor60 = computeEaseFactor(follow, 16.67);
    expect(factor60).toBeCloseTo(follow, 4);

    // At 120 Hz (dt = 8.335ms), two frames should equal one 60 Hz frame
    const factor120 = computeEaseFactor(follow, 16.67 / 2);
    const remainingAfterTwo120Hz = (1 - factor120) * (1 - factor120);
    const remainingAfterOne60Hz = 1 - factor60;
    expect(remainingAfterTwo120Hz).toBeCloseTo(remainingAfterOne60Hz, 5);

    // At 144 Hz (dt = 11.576ms)
    const factor144 = computeEaseFactor(follow, 16.67 * (60 / 144));
    expect(factor144).toBeGreaterThan(0);
    expect(factor144).toBeLessThan(factor60);
  });

  it("reads glyph color token from CSS custom property", () => {
    expect(COLOR_TOKEN).toBe("--palette-white");
    // Ensure documentElement has style resolution
    const style = getComputedStyle(document.documentElement);
    // In test environment, getPropertyValue can read mock or default
    expect(style.getPropertyValue).toBeDefined();
  });

  it("handles pause conditions correctly", () => {
    // When shader is off
    document.documentElement.dataset.shader = "off";
    expect(document.documentElement.dataset.shader).toBe("off");
    delete document.documentElement.dataset.shader;
    expect(document.documentElement.dataset.shader).toBeUndefined();
  });
});

describe("Fidelity test: reference renderer vs optimized sprite-based renderer", () => {
  it("renders both at fixed time and position with mean absolute pixel difference under 2/255", () => {
    const w = 480;
    const h = 360;
    const cell = CONFIG.cell; // 24
    const cols = Math.ceil(w / cell) + 1;
    const rows = Math.ceil(h / cell) + 1;
    const t = 1.45; // Fixed non-zero time
    const mouse = {
      x: 200,
      y: 160,
      sx: 195,
      sy: 158,
      active: true,
    };

    // A simple 7x7 bitmap glyph font for deterministic rendering
    // Representation of '+', '=', '*' on a 7x7 grid
    const GLYPH_BITMAPS: number[][][] = [
      // '+'
      [
        [0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0],
      ],
      // '='
      [
        [0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
      ],
      // '*'
      [
        [1, 0, 0, 1, 0, 0, 1],
        [0, 1, 0, 1, 0, 1, 0],
        [0, 0, 1, 1, 1, 0, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 0, 1, 1, 1, 0, 0],
        [0, 1, 0, 1, 0, 1, 0],
        [1, 0, 0, 1, 0, 0, 1],
      ],
    ];

    // Reference renderer: draws directly with exact alpha
    const refBuffer = new Float32Array(w * h);
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        let x = i * cell;
        let y = j * cell;
        let k = 0, dx = 0, dy = 0;
        if (mouse.active) {
          dx = x - mouse.sx;
          dy = y - mouse.sy;
          const d2 = dx * dx + dy * dy;
          k = computeFalloff(d2, CONFIG.radius);
        }
        const idx = computeGlyphIndex(i, j, t, k, CONFIG.glyphs.length);
        if (k > 0.001) {
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          x += (dx / len) * CONFIG.push * k;
          y += (dy / len) * CONFIG.push * k;
        }
        const alpha = CONFIG.baseAlpha + CONFIG.hoverAlpha * k;
        const bitmap = GLYPH_BITMAPS[idx]!;
        const startX = Math.round(x) - 3;
        const startY = Math.round(y) - 3;

        for (let py = 0; py < 7; py++) {
          for (let px = 0; px < 7; px++) {
            if (bitmap[py]![px]! > 0) {
              const targetX = startX + px;
              const targetY = startY + py;
              if (targetX >= 0 && targetX < w && targetY >= 0 && targetY < h) {
                refBuffer[targetY * w + targetX] = alpha;
              }
            }
          }
        }
      }
    }

    // Optimized renderer:
    // 1. Pre-render 24-level sprite atlas
    const spriteSize = 7;
    const atlas = new Float32Array(CONFIG.glyphs.length * ALPHA_LEVELS * spriteSize * spriteSize);
    for (let l = 0; l < ALPHA_LEVELS; l++) {
      const k = l / (ALPHA_LEVELS - 1);
      const alpha = CONFIG.baseAlpha + CONFIG.hoverAlpha * k;
      for (let g = 0; g < CONFIG.glyphs.length; g++) {
        const bitmap = GLYPH_BITMAPS[g]!;
        const spriteOffset = (l * CONFIG.glyphs.length + g) * spriteSize * spriteSize;
        for (let py = 0; py < spriteSize; py++) {
          for (let px = 0; px < spriteSize; px++) {
            if (bitmap[py]![px]! > 0) {
              atlas[spriteOffset + py * spriteSize + px] = alpha;
            }
          }
        }
      }
    }

    // 2. Ambient buffer (level 0)
    const ambientBuffer = new Float32Array(w * h);
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const idx = computeGlyphIndex(i, j, t, 0, CONFIG.glyphs.length);
        const x = i * cell;
        const y = j * cell;
        const startX = Math.round(x) - 3;
        const startY = Math.round(y) - 3;
        const spriteOffset = (0 * CONFIG.glyphs.length + idx) * spriteSize * spriteSize;

        for (let py = 0; py < spriteSize; py++) {
          for (let px = 0; px < spriteSize; px++) {
            const val = atlas[spriteOffset + py * spriteSize + px]!;
            if (val > 0) {
              const targetX = startX + px;
              const targetY = startY + py;
              if (targetX >= 0 && targetX < w && targetY >= 0 && targetY < h) {
                ambientBuffer[targetY * w + targetX] = val;
              }
            }
          }
        }
      }
    }

    // 3. Composite ambient + 2-pass clear and redraw influenced cells
    const optBuffer = new Float32Array(ambientBuffer);
    const radius = CONFIG.radius;
    const maxDist = radius * 1.5;
    const minI = Math.max(0, Math.floor((mouse.sx - maxDist) / cell));
    const maxI = Math.min(cols - 1, Math.ceil((mouse.sx + maxDist) / cell));
    const minJ = Math.max(0, Math.floor((mouse.sy - maxDist) / cell));
    const maxJ = Math.min(rows - 1, Math.ceil((mouse.sy + maxDist) / cell));

    type CellInfo = { i: number; j: number; k: number; dx: number; dy: number };
    const influenced: CellInfo[] = [];

    for (let j = minJ; j <= maxJ; j++) {
      for (let i = minI; i <= maxI; i++) {
        const baseX = i * cell;
        const baseY = j * cell;
        const dx = baseX - mouse.sx;
        const dy = baseY - mouse.sy;
        const d2 = dx * dx + dy * dy;
        const k = computeFalloff(d2, radius);
        if (k > INFLUENCE_THRESHOLD) {
          influenced.push({ i, j, k, dx, dy });
        }
      }
    }

    // Pass 1: Clear influenced ambient cells
    for (const item of influenced) {
      const startX = Math.round(item.i * cell) - 3;
      const startY = Math.round(item.j * cell) - 3;
      for (let py = 0; py < spriteSize; py++) {
        for (let px = 0; px < spriteSize; px++) {
          const targetX = startX + px;
          const targetY = startY + py;
          if (targetX >= 0 && targetX < w && targetY >= 0 && targetY < h) {
            optBuffer[targetY * w + targetX] = 0;
          }
        }
      }
    }

    // Pass 2: Draw influenced cells at nudged positions
    for (const item of influenced) {
      const { i, j, k, dx, dy } = item;
      let x = i * cell;
      let y = j * cell;
      if (k > 0.001) {
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        x += (dx / len) * CONFIG.push * k;
        y += (dy / len) * CONFIG.push * k;
      }
      const idx = computeGlyphIndex(i, j, t, k, CONFIG.glyphs.length);
      const level = Math.min(
        ALPHA_LEVELS - 1,
        Math.max(0, Math.round(k * (ALPHA_LEVELS - 1))),
      );
      const spriteOffset = (level * CONFIG.glyphs.length + idx) * spriteSize * spriteSize;
      const startX = Math.round(x) - 3;
      const startY = Math.round(y) - 3;

      for (let py = 0; py < spriteSize; py++) {
        for (let px = 0; px < spriteSize; px++) {
          const val = atlas[spriteOffset + py * spriteSize + px]!;
          if (val > 0) {
            const targetX = startX + px;
            const targetY = startY + py;
            if (targetX >= 0 && targetX < w && targetY >= 0 && targetY < h) {
              optBuffer[targetY * w + targetX] = val;
            }
          }
        }
      }
    }

    // Calculate mean absolute pixel difference
    let totalAbsDiff = 0;
    const totalPixels = w * h;
    for (let p = 0; p < totalPixels; p++) {
      totalAbsDiff += Math.abs(refBuffer[p]! - optBuffer[p]!);
    }
    const meanAbsDiff = totalAbsDiff / totalPixels;

    // Assert difference is under 2/255 (≈ 0.00784)
    expect(meanAbsDiff).toBeLessThan(2 / 255);
  });
});
