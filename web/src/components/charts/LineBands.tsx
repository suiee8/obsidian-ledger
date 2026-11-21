import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { fmtMoney } from "../../lib/format";
import type { MonteCarlo } from "../../lib/insights";
import { prefersReducedMotion } from "../../lib/theme";
import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";

type Fan = NonNullable<MonteCarlo["fan"]>;

/**
 * Monte Carlo fan: the middle 50% and middle 90% of simulated equity paths, and the median.
 * `start` is where every path begins, drawn as a dashed reference line.
 */
export function MonteCarloFan({ fan, label, start }: { fan: Fan; label: string; start: number }) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(() => {
    const x = [0, ...fan.map((row) => row.trade)];
    // Every path starts at the same point, so the fan opens from a single value.
    const withStart = (values: number[]) => [start, ...values];
    // A band is drawn as a transparent base line plus a stacked area for the gap above it.
    const band = (name: string, low: number[], high: number[], stack: string, color: string) => [
      {
        name: `${name} base`,
        type: "line" as const,
        stack,
        data: low,
        symbol: "none",
        lineStyle: { opacity: 0 },
        silent: true,
      },
      {
        name,
        type: "line" as const,
        stack,
        data: high.map((value, index) => value - (low[index] ?? 0)),
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color },
        silent: true,
      },
    ];
    return {
      animation: !prefersReducedMotion(),
      grid: { left: 72, right: 16, top: 16, bottom: 44 },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 14px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
        formatter: (params: unknown) => {
          const index = (params as { dataIndex?: number }[])[0]?.dataIndex ?? 0;
          const row = index === 0 ? undefined : fan[index - 1];
          if (!row) return `Start: ${fmtMoney(start)}`;
          return [
            `After ${row.trade} trades`,
            `Best 5%: ${fmtMoney(row.p95)}`,
            `Upper quarter: ${fmtMoney(row.p75)}`,
            `Median: ${fmtMoney(row.p50)}`,
            `Lower quarter: ${fmtMoney(row.p25)}`,
            `Worst 5%: ${fmtMoney(row.p5)}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: x,
        name: "Trades from now",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim },
        axisLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: palette.dim, formatter: (value: number) => fmtMoney(value) },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.06 } },
      },
      series: [
        ...band("Middle 90%", withStart(fan.map((r) => r.p5)), withStart(fan.map((r) => r.p95)), "wide", `${palette.royal}26`),
        ...band("Middle 50%", withStart(fan.map((r) => r.p25)), withStart(fan.map((r) => r.p75)), "narrow", `${palette.royal}4d`),
        {
          name: "Median",
          type: "line",
          data: withStart(fan.map((r) => r.p50)),
          symbol: "none",
          lineStyle: { color: palette.ice, width: 2 },
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: palette.dim, type: "dashed", width: 1 },
            data: [{ yAxis: start }],
          },
        },
      ],
    };
  }, [fan, palette, start]);
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-fan" role="img" aria-label={label} />;
}

type Histogram = NonNullable<MonteCarlo["final_histogram"]>;

/**
 * Where the simulated paths end up: how many of them finished in each range of equity. Bars at or
 * above the starting point are profit, the rest are loss, and the dashed line marks the median.
 */
export function EndingHistogram({
  histogram,
  start,
  median,
  label,
}: {
  histogram: Histogram;
  start: number;
  median: number;
  label: string;
}) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(() => {
    const { edges, counts } = histogram;
    const total = counts.reduce((sum, count) => sum + count, 0) || 1;
    const centers = counts.map((_, index) => ((edges[index] ?? 0) + (edges[index + 1] ?? 0)) / 2);
    return {
      animation: !prefersReducedMotion(),
      grid: { left: 16, right: 16, top: 16, bottom: 44 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 14px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
        formatter: (params: unknown) => {
          const index = (params as { dataIndex?: number }[])[0]?.dataIndex ?? 0;
          const share = ((counts[index] ?? 0) / total) * 100;
          return [
            `${fmtMoney(edges[index])} to ${fmtMoney(edges[index + 1])}`,
            `${share.toFixed(1)}% of paths`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: centers.map((center) => fmtMoney(center)),
        name: "Equity after the last trade",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim, hideOverlap: true },
        axisLine: { lineStyle: { color: palette.line } },
        axisTick: { show: false },
      },
      yAxis: { type: "value", show: false },
      series: [
        {
          type: "bar",
          barCategoryGap: "6%",
          data: counts.map((count, index) => ({
            value: count,
            itemStyle: {
              color: (centers[index] ?? 0) >= start ? palette.profit : palette.loss,
              opacity: 0.8,
              borderRadius: [4, 4, 0, 0],
            },
          })),
          markLine: {
            silent: true,
            symbol: "none",
            label: { formatter: "median", color: palette.muted, position: "end" },
            lineStyle: { color: palette.ice, type: "dashed", width: 1 },
            data: [{ xAxis: nearestBin(centers, median) }],
          },
        },
      ],
    };
  }, [histogram, start, median, palette]);
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-fan" role="img" aria-label={label} />;
}

function nearestBin(centers: readonly number[], value: number): number {
  let best = 0;
  centers.forEach((center, index) => {
    if (Math.abs(center - value) < Math.abs((centers[best] ?? 0) - value)) best = index;
  });
  return best;
}

interface OverlayProps {
  x: readonly number[];
  baseline: readonly number[];
  simulated: readonly number[];
  label: string;
}

/** Cumulative P&L of your trades and of the same trades under the rules, one on the other. */
export function SimulatorOverlay({ x, baseline, simulated, label }: OverlayProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(
    () => ({
      animation: !prefersReducedMotion(),
      grid: { left: 72, right: 16, top: 32, bottom: 44 },
      legend: { top: 0, textStyle: { color: palette.muted } },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 14px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
        valueFormatter: (value: unknown) => (typeof value === "number" ? fmtMoney(value) : ""),
      },
      xAxis: {
        type: "category",
        data: [...x],
        name: "Trades, in order of exit",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: palette.muted },
        axisLabel: { color: palette.dim, hideOverlap: true },
        axisLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: palette.dim, formatter: (value: number) => fmtMoney(value) },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.06 } },
      },
      series: [
        {
          name: "Your trades",
          type: "line",
          data: [...baseline],
          symbol: "none",
          lineStyle: { color: palette.dim, width: 2 },
        },
        {
          name: "With the rules",
          type: "line",
          data: [...simulated],
          symbol: "none",
          lineStyle: { color: palette.royalSoft, width: 2.5 },
          areaStyle: { color: `${palette.royal}26` },
        },
      ],
    }),
    [x, baseline, simulated, palette],
  );
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-fan" role="img" aria-label={label} />;
}
