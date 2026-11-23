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

const axisMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

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
      useUTC: true,
      grid: [
        { left: 52, right: 16, top: 12, height: "53%" },
        { left: 52, right: 16, top: "66%", bottom: 24 },
      ],
      xAxis: [
        { type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
        { type: "time", gridIndex: 1, axisLabel: { color: palette.ink, hideOverlap: true }, axisLine: { lineStyle: { color: palette.line } }, splitLine: { show: false } },
      ],
      yAxis: [
        {
          type: "value",
          gridIndex: 0,
          axisLabel: { color: palette.ink, formatter: (value: number) => axisMoney.format(value) },
          splitLine: { lineStyle: { color: palette.white, opacity: 0.06 } },
        },
        {
          type: "value",
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { color: palette.ink, formatter: (value: number) => axisMoney.format(value) },
          splitLine: { lineStyle: { color: palette.white, opacity: 0.06 } },
        },
      ],
      axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "border-radius: 10px;",
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
          lineStyle: { color: palette.royalSoft, width: 2 },
          emphasis: { focus: "series", lineStyle: { color: palette.white, width: 2.5 } },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: `${palette.royal}73` },
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
          lineStyle: { color: palette.loss, width: 1, opacity: 0.7 },
          areaStyle: { color: `${palette.loss}33` },
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
