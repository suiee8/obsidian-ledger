import { useMemo } from "react";
import type { EChartsOption } from "echarts";

import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";
import { fmtMoney } from "../../lib/format";
import { prefersReducedMotion } from "../../lib/theme";
import type { DashboardData } from "../../lib/dashboard";

interface EquityAuroraProps {
  equity: DashboardData["equity"];
}

/**
 * Equity curve as a glowing line with a gradient fill, and drawdown as an inverted ribbon in
 * its own band beneath it.
 */
export function EquityAurora({ equity }: EquityAuroraProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(() => {
    const times = equity.points.map((point) => Date.parse(point.t));
    const equityData = equity.points.map((point, index) => [times[index], point.equity]);
    const drawdownData = equity.points.map((point, index) => [times[index], point.drawdown]);
    return {
      animation: !prefersReducedMotion(),
      grid: [
        { left: 56, right: 16, top: 16, height: "58%" },
        { left: 56, right: 16, top: "70%", bottom: 28 },
      ],
      xAxis: [
        { type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
        { type: "time", gridIndex: 1, axisLabel: { color: palette.dim }, axisLine: { lineStyle: { color: palette.line } }, splitLine: { show: false } },
      ],
      yAxis: [
        {
          type: "value",
          gridIndex: 0,
          axisLabel: { color: palette.dim, formatter: (value: number) => fmtMoney(value).replace(/\.00$/, "") },
          splitLine: { lineStyle: { color: palette.line, opacity: 0.35 } },
        },
        {
          type: "value",
          gridIndex: 1,
          axisLabel: { color: palette.dim, formatter: (value: number) => fmtMoney(value).replace(/\.00$/, "") },
          splitLine: { show: false },
        },
      ],
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: unknown) => fmtMoney(Number(value)),
      },
      series: [
        {
          name: "Equity",
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: equityData,
          showSymbol: false,
          lineStyle: { color: palette.royal, width: 2, shadowBlur: 12, shadowColor: palette.royal },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: `${palette.royal}66` },
                { offset: 1, color: `${palette.royal}00` },
              ],
            },
          },
        },
        {
          name: "Drawdown",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: drawdownData,
          showSymbol: false,
          lineStyle: { color: palette.loss, width: 1 },
          areaStyle: { color: `${palette.loss}55` },
        },
      ],
    };
  }, [equity, palette]);
  const ref = useChart(option);
  return (
    <div
      ref={ref}
      className="chart chart-equity"
      role="img"
      aria-label={`Equity curve over ${equity.source_points} trades${equity.downsampled ? ", downsampled for display" : ""}`}
    />
  );
}
