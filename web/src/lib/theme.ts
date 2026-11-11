export interface ChartPalette {
  profit: string;
  loss: string;
  royal: string;
  royalSoft: string;
  ice: string;
  ink: string;
  muted: string;
  dim: string;
  line: string;
  surface: string;
}

const FALLBACK: ChartPalette = {
  profit: "#3DDC97",
  loss: "#FF5C6C",
  royal: "#4169E1",
  royalSoft: "#94ADF6",
  ice: "#C9D6FF",
  ink: "#E8ECF4",
  muted: "#9AA4B8",
  dim: "#6B7488",
  line: "#262C38",
  surface: "#11141A",
};

/**
 * Chart colors come from the CSS variables on the document, so the color-blind setting and any
 * future theme change apply to charts without a rebuild.
 */
// Color-blind mode: profit becomes royal blue and loss becomes amber (master prompt, Section 7).
const FALLBACK_COLOR_BLIND: Partial<ChartPalette> = { profit: "#4169E1", loss: "#F5B84B" };

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
    ice: read("--ice", base.ice),
    ink: read("--ink", base.ink),
    muted: read("--muted", base.muted),
    dim: read("--dim", base.dim),
    line: read("--line", base.line),
    surface: read("--surface-1", base.surface),
  };
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
