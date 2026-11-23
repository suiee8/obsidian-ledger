export interface GlyphFieldConfig {
  glyphs: string[];
  cell: number;
  fontSize: number;
  baseAlpha: number;
  hoverAlpha: number;
  radius: number;
  follow: number;
  speed: number;
  push: number;
}

export const CONFIG: GlyphFieldConfig = {
  glyphs: ["+", "=", "*"],
  cell: 24,
  fontSize: 15,
  baseAlpha: 0.1,
  hoverAlpha: 0.85,
  radius: 190,
  follow: 0.12,
  speed: 0.45,
  push: 5,
};

export const COLOR_TOKEN = "--palette-white";
export const FONT_TOKEN = "--font-mono";
export const ALPHA_LEVELS = 24;
export const INFLUENCE_THRESHOLD = 0.01;

/**
 * Travelling-wave formula deciding which glyph shows.
 */
export function computeGlyphIndex(
  i: number,
  j: number,
  t: number,
  k: number,
  glyphCount: number,
): number {
  const n =
    Math.sin(i * 0.31 + t * 2.1) +
    Math.cos(j * 0.27 - t * 1.7) +
    Math.sin((i + j) * 0.14 + t * 1.1) +
    k * 1.6 * Math.sin(t * 6 + i * 0.5 - j * 0.5);
  return (((Math.floor((n + 3.2) * 0.9) % glyphCount) + glyphCount) % glyphCount);
}

/**
 * Proximity to cursor falloff.
 */
export function computeFalloff(d2: number, radius: number): number {
  const r2 = radius * radius;
  return Math.exp((-d2 / r2) * 2.2);
}

/**
 * Frame-rate-independent easing factor.
 */
export function computeEaseFactor(follow: number, dt: number): number {
  return 1 - Math.pow(1 - follow, dt / 16.67);
}
