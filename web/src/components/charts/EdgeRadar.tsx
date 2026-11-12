import { useMemo } from "react";
import type { EChartsOption } from "echarts";

import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";
import { prefersReducedMotion } from "../../lib/theme";
import type { DashboardData } from "../../lib/dashboard";

interface EdgeRadarProps {
  radar: DashboardData["radar"];
}

const AXIS_LABELS: Record<string, string> = {
  win_rate: "Win rate",
  payoff: "Payoff",
  expectancy_r: "Expectancy (R)",
  consistency: "Consistency",
  discipline: "Discipline",
  risk_control: "Risk control",
};
const MAX_SETUPS = 5;

/** One polygon per setup, axes scaled 0 to 100 across the setups shown. */
export function EdgeRadar({ radar }: EdgeRadarProps) {
  const palette = useChartPalette();
  const setups = useMemo(() => radar.setups.slice(0, MAX_SETUPS), [radar.setups]);
  const option = useMemo<EChartsOption>(() => {
    const colors = [palette.royal, palette.royalSoft, palette.ice, palette.royal400, palette.royal600];
    return {
      animation: !prefersReducedMotion(),
      tooltip: {
        trigger: "item",
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 12px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
      },
      legend: {
        bottom: 0,
        textStyle: { color: palette.muted },
        data: setups.map((setup) => (setup.low_confidence ? `${setup.setup} (low n)` : setup.setup)),
      },
      radar: {
        radius: "62%",
        indicator: radar.axes.map((axis) => ({ name: AXIS_LABELS[axis] ?? axis, max: 100 })),
        axisName: { color: palette.muted },
        axisLine: { lineStyle: { color: palette.line } },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.06 } },
        splitArea: { show: false },
      },
      series: [
        {
          type: "radar",
          data: setups.map((setup, index) => ({
            name: setup.low_confidence ? `${setup.setup} (low n)` : setup.setup,
            value: setup.normalized.map((value) => value ?? 0),
            lineStyle: { color: colors[index % colors.length], width: 2 },
            itemStyle: { color: colors[index % colors.length] },
            areaStyle: { color: colors[index % colors.length], opacity: 0.12 },
            symbolSize: 4,
          })),
        },
      ],
    };
  }, [palette, radar.axes, setups]);
  const ref = useChart(option);
  if (setups.length === 0) {
    return <p className="muted">Add setups to your trades to compare edges.</p>;
  }
  return (
    <div
      ref={ref}
      className="chart chart-radar"
      role="img"
      aria-label={`Edge radar for ${setups.length} setups across six axes`}
    />
  );
}
