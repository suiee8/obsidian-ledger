import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { prefersReducedMotion } from "../../lib/theme";
import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";

interface BarSeriesProps {
  label: string;
  labels: readonly string[];
  values: readonly (number | null)[];
  format: (value: number) => string;
  /** Color bars green above zero and red below it. Otherwise they are royal blue. */
  signed: boolean;
}

/** Horizontal bars, one per category. The height follows the number of bars. */
export function BarSeries({ label, labels, values, format, signed }: BarSeriesProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(
    () => ({
      animation: !prefersReducedMotion(),
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        valueFormatter: (value: unknown) => (typeof value === "number" ? format(value) : "no data"),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: palette.dim, formatter: (value: number) => format(value) },
        splitLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: [...labels],
        axisLabel: { color: palette.muted },
        axisLine: { lineStyle: { color: palette.line } },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 22,
          data: values.map((value) => ({
            value,
            itemStyle: {
              color: signed ? ((value ?? 0) >= 0 ? palette.profit : palette.loss) : palette.royal,
              borderRadius: 4,
            },
          })),
          label: {
            show: true,
            position: "right",
            color: palette.muted,
            formatter: (params: { value?: unknown }) =>
              typeof params.value === "number" ? format(params.value) : "",
          },
        },
      ],
    }),
    [labels, values, format, signed, palette],
  );
  const ref = useChart(option);
  const height = Math.max(200, labels.length * 30 + 40);
  return <div ref={ref} className="chart" style={{ height, minHeight: 0 }} role="img" aria-label={label} />;
}

interface GroupedBarsProps {
  label: string;
  categories: readonly string[];
  wins: readonly number[];
  losses: readonly number[];
  xName: string;
  yName: string;
}

/** Winning and losing counts side by side for each category. */
export function GroupedBars({ label, categories, wins, losses, xName, yName }: GroupedBarsProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(
    () => ({
      animation: !prefersReducedMotion(),
      grid: { left: 44, right: 12, top: 28, bottom: 44 },
      legend: { top: 0, textStyle: { color: palette.muted } },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
      },
      xAxis: {
        type: "category",
        data: [...categories],
        name: xName,
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim },
        axisLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "value",
        name: yName,
        minInterval: 1,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim },
        splitLine: { lineStyle: { color: palette.line } },
      },
      series: [
        { name: "Winning runs", type: "bar", data: [...wins], itemStyle: { color: palette.profit, borderRadius: 3 } },
        { name: "Losing runs", type: "bar", data: [...losses], itemStyle: { color: palette.loss, borderRadius: 3 } },
      ],
    }),
    [categories, wins, losses, xName, yName, palette],
  );
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-r" role="img" aria-label={label} />;
}

interface DayBarsProps {
  label: string;
  days: readonly string[];
  values: readonly number[];
  flagged: readonly boolean[];
  name: string;
  /** A dashed line at this value, such as the trades-per-day limit. */
  threshold?: { value: number; label: string };
}

/** One bar per day. Bars that cross the rule for that behavior are drawn in the warning color. */
export function DayBars({ label, days, values, flagged, name, threshold }: DayBarsProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(
    () => ({
      animation: !prefersReducedMotion(),
      grid: { left: 44, right: 12, top: 16, bottom: 44 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
      },
      xAxis: {
        type: "category",
        data: [...days],
        axisLabel: { color: palette.dim, hideOverlap: true },
        axisLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: palette.dim },
        splitLine: { lineStyle: { color: palette.line } },
      },
      series: [
        {
          name,
          type: "bar",
          barMaxWidth: 14,
          data: values.map((value, index) => ({
            value,
            itemStyle: { color: flagged[index] ? palette.loss : palette.royal, borderRadius: 2 },
          })),
          markLine: threshold
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: palette.royalSoft, type: "dashed" },
                label: { color: palette.muted, formatter: threshold.label },
                data: [{ yAxis: threshold.value }],
              }
            : undefined,
        },
      ],
    }),
    [days, values, flagged, name, threshold, palette],
  );
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-timeline" role="img" aria-label={label} />;
}
