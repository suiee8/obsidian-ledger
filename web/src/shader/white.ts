/** The most the white highlights may add, as a share of the final pixel luminance. */
export const WHITE_CAP = 0.15;

/**
 * How much white one pixel may add. The same formula runs in fragment.glsl.
 * `wanted` is the highlight strength (0 to 1) and `baseLuminance` the pixel before white is added.
 * Adding `w` of white gives a white share of w / (baseLuminance + w), which this keeps at or below `cap`.
 */
export function cappedWhite(baseLuminance: number, wanted: number, cap = WHITE_CAP): number {
  const limit = (cap / (1 - cap)) * Math.max(0, baseLuminance);
  return Math.min(Math.max(0, wanted), limit);
}

/** Whether the pause toggle starts on: the saved choice wins, otherwise follow the OS motion setting. */
export function initialBackgroundPaused(stored: string | null, prefersReducedMotion: boolean): boolean {
  if (stored === "true") return true;
  if (stored === "false") return false;
  return prefersReducedMotion;
}
