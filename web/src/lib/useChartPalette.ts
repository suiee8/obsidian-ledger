import { useMemo } from "react";

import { useUi } from "../state/ui";
import { readChartPalette, type ChartPalette } from "./theme";

/** The chart palette for the current color-blind setting. */
export function useChartPalette(): ChartPalette {
  const colorBlind = useUi((state) => state.colorBlind);
  return useMemo(() => readChartPalette(colorBlind), [colorBlind]);
}
