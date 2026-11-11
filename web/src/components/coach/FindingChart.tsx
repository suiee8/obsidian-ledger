import { useMemo } from "react";
import type { EChartsOption } from "echarts";

import { prefersReducedMotion } from "../../lib/theme";
import type { CoachFinding } from "../../lib/schemas";
import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";

interface FindingChartProps {
  finding: CoachFinding;
}

/** Average result per trade for the slice and for your other trades, side by side.
 *  The rest-of-trades bar is derived: slice average minus the measured gap. */
export default function FindingChart({ finding }: FindingChartProps) {
  const palette = useChartPalette();
  const slice = finding.mean_currency.value;
  const gap = finding.effect_currency.value;
  const rest = slice !== null && gap !== null ? slice - gap : null;
  const interval = finding.interval_currency;
  const option = useMemo<EChartsOption>(() => {
    const tone = (value: number | null) => (value !== null && value < 0 ? palette.loss : palette.profit);
    const values = [rest, slice];
    return {
      animation: !prefersReducedMotion(),
      grid: { left: 92, right: 16, top: 6, bottom: 22 },
      xAxis: {
        type: "value",
        axisLabel: { color: palette.dim },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.35 } },
      },
      yAxis: {
        type: "category",
        data: ["Other trades", "This slice"],
        axisLabel: { color: palette.muted },
        axisLine: { lineStyle: { color: palette.line } },
      },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "bar",
          barWidth: 14,
          data: values.map((value) => ({ value, itemStyle: { color: tone(value) } })),
        },
      ],
    };
  }, [palette, rest, slice]);
  const ref = useChart(option);
  const range =
    interval?.low.display && interval.high.display
      ? ` The gap's 95% interval runs from ${interval.low.display} to ${interval.high.display}.`
      : "";
  return (
    <div
      ref={ref}
      className="chart chart-mini"
      role="img"
      aria-label={`Average per trade: this slice ${finding.mean_currency.display}, other trades ${
        rest === null ? "not available" : rest.toFixed(2)
      }.${range}`}
    />
  );
}
