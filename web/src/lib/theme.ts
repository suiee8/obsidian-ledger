import { palette } from "../tokens";

export interface ChartPalette {
  profit: string;
  loss: string;
  royal: string;
  royalSoft: string;
  royal400: string;
  royal600: string;
  royal700: string;
  ice: string;
  white: string;
  ink: string;
  muted: string;
  dim: string;
  line: string;
  surface: string;
}

const FALLBACK: ChartPalette = {
  profit: palette.profit,
  loss: palette.loss,
  royal: palette.royal500,
  royalSoft: palette.royal300,
  royal400: palette.royal400,
  royal600: palette.royal600,
  royal700: palette.royal700,
  ice: palette.ice,
  white: palette.white,
  ink: palette.ink,
  muted: palette.muted,
  dim: palette.muted,
  line: palette.border,
  surface: palette.surface1,
};

/**
 * Chart colors come from the CSS variables on the document, so the color-blind setting and any
 * future theme change apply to charts without a rebuild.
 */
const FALLBACK_COLOR_BLIND: Partial<ChartPalette> = { profit: palette.royal500, loss: "#F5B84B" };

export function readChartPalette(colorBlind = false): ChartPalette {
  const base: ChartPalette = colorBlind ? { ...FALLBACK, ...FALLBACK_COLOR_BLIND } : FALLBACK;
  if (typeof document === "undefined") return base;
  const style = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string): string => {
    const value = style.getPropertyValue(name).trim();
    return value === "" ? fallback : value;
  };
  return {
    profit: read("--pnl-profit", base.profit),
    loss: read("--pnl-loss", base.loss),
    royal: read("--royal-500", base.royal),
    royalSoft: read("--royal-300", base.royalSoft),
    royal400: read("--palette-royal400", base.royal400),
    royal600: read("--palette-royal600", base.royal600),
    royal700: read("--palette-royal700", base.royal700),
    ice: read("--ice", base.ice),
    white: read("--palette-white", base.white),
    ink: read("--ink", base.ink),
    muted: read("--muted", base.muted),
    dim: read("--muted", base.dim),
    line: read("--line", base.line),
    surface: read("--surface-1", base.surface),
  };
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
