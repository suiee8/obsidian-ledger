import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { fmtMoney } from "../../lib/format";
import type { MonteCarlo } from "../../lib/phase4";
import { prefersReducedMotion } from "../../lib/theme";
import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";

type Fan = NonNullable<MonteCarlo["fan"]>;

/** Monte Carlo fan: the middle 50% and middle 90% of simulated equity paths, and the median. */
export function MonteCarloFan({ fan, label }: { fan: Fan; label: string }) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(() => {
    const x = fan.map((row) => row.trade);
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
        extraCssText: "backdrop-filter: blur(12px); border-radius: 12px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
        formatter: (params: unknown) => {
          const index = (params as { dataIndex?: number }[])[0]?.dataIndex ?? 0;
          const row = fan[index];
          if (!row) return "";
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
        ...band("Middle 90%", fan.map((r) => r.p5), fan.map((r) => r.p95), "wide", `${palette.royal}26`),
        ...band("Middle 50%", fan.map((r) => r.p25), fan.map((r) => r.p75), "narrow", `${palette.royal}4d`),
        {
          name: "Median",
          type: "line",
          data: fan.map((r) => r.p50),
          symbol: "none",
          lineStyle: { color: palette.ice, width: 2 },
        },
      ],
    };
  }, [fan, palette]);
  const ref = useChart(option);
  return <div ref={ref} className="chart chart-fan" role="img" aria-label={label} />;
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
        extraCssText: "backdrop-filter: blur(12px); border-radius: 12px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
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
