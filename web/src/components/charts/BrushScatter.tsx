import type { EChartsOption } from "echarts";
import { useEffect, useMemo, useRef } from "react";

import { echarts } from "../../lib/echarts";
import { prefersReducedMotion } from "../../lib/theme";
import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";

export interface BrushRange {
  x: [number, number];
  y: [number, number];
}

interface BrushScatterProps {
  label: string;
  xs: readonly (number | null)[];
  ys: readonly (number | null)[];
  /** Decides the point color: above zero is a win, below is a loss. */
  outcome: readonly number[];
  xType: "time" | "value";
  xName: string;
  yName: string;
  formatX: (value: number) => string;
  formatY: (value: number) => string;
  onBrush: (range: BrushRange | null) => void;
  /** Change this value to clear the drawn rectangle. */
  clearToken: number;
  className?: string;
}

const CURSOR = {
  type: "takeGlobalCursor",
  key: "brush",
  brushOption: { brushType: "rect", brushMode: "single" },
} as const;

/** A scatter of one point per trade. Drag on it to draw a rectangle and pick those trades. */
export function BrushScatter({
  label,
  xs,
  ys,
  outcome,
  xType,
  xName,
  yName,
  formatX,
  formatY,
  onBrush,
  clearToken,
  className = "chart-scatter",
}: BrushScatterProps) {
  const palette = useChartPalette();
  const chartRef = useRef<echarts.ECharts | null>(null);
  const brushRef = useRef(onBrush);
  brushRef.current = onBrush;

  const option = useMemo<EChartsOption>(() => {
    const wins: [number, number][] = [];
    const losses: [number, number][] = [];
    for (let i = 0; i < xs.length; i++) {
      const x = xs[i];
      const y = ys[i];
      if (x === null || x === undefined || y === null || y === undefined) continue;
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      ((outcome[i] ?? 0) >= 0 ? wins : losses).push([x, y]);
    }
    const series = (name: string, data: [number, number][], color: string) => ({
      name,
      type: "scatter" as const,
      data,
      large: true,
      largeThreshold: 1500,
      symbolSize: 6,
      itemStyle: { color: `${color}b3` },
      emphasis: { itemStyle: { color } },
    });
    return {
      animation: !prefersReducedMotion(),
      useUTC: true,
      grid: { left: 64, right: 20, top: 24, bottom: 56 },
      tooltip: {
        trigger: "item",
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 12px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
        formatter: (params: unknown) => {
          const value = (params as { value?: [number, number] }).value;
          return value ? `${xName}: ${formatX(value[0])}<br/>${yName}: ${formatY(value[1])}` : "";
        },
      },
      xAxis: {
        type: xType,
        name: xName,
        nameLocation: "middle",
        nameGap: 34,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim, formatter: (value: number) => formatX(value) },
        axisLine: { lineStyle: { color: palette.line } },
        splitLine: { show: false },
        scale: true,
      },
      yAxis: {
        type: "value",
        name: yName,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim, formatter: (value: number) => formatY(value) },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.06 } },
        scale: true,
      },
      brush: {
        xAxisIndex: 0,
        yAxisIndex: 0,
        brushType: "rect",
        brushMode: "single",
        transformable: true,
        throttleType: "debounce",
        throttleDelay: 120,
        brushStyle: {
          borderWidth: 1,
          color: `${palette.royal}33`,
          borderColor: palette.royalSoft,
        },
      },
      series: [series("Winners", wins, palette.profit), series("Losers", losses, palette.loss)],
    };
  }, [xs, ys, outcome, xType, xName, yName, formatX, formatY, palette]);

  const ref = useChart(option, (chart) => {
    chartRef.current = chart;
    chart?.on("brushEnd", (event: unknown) => {
      const areas = (event as { areas?: { coordRange?: unknown }[] }).areas ?? [];
      const range = areas[0]?.coordRange as [[number, number], [number, number]] | undefined;
      brushRef.current(range ? { x: range[0], y: range[1] } : null);
    });
  });

  // setOption resets the brush tool, so arm it again after every option change.
  useEffect(() => {
    chartRef.current?.dispatchAction(CURSOR);
  }, [option]);

  useEffect(() => {
    if (clearToken > 0) chartRef.current?.dispatchAction({ type: "brush", areas: [] });
  }, [clearToken]);

  return <div ref={ref} className={`chart ${className}`} role="img" aria-label={label} />;
}
