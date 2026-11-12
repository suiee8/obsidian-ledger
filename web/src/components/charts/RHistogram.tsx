import { useMemo } from "react";
import type { EChartsOption } from "echarts";

import { useChart } from "../../lib/useChart";
import { useChartPalette } from "../../lib/useChartPalette";
import { fmtNumber } from "../../lib/format";
import { prefersReducedMotion } from "../../lib/theme";
import type { DashboardData } from "../../lib/dashboard";

interface RHistogramProps {
  histogram: DashboardData["r_histogram"];
}

export function RHistogram({ histogram }: RHistogramProps) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption>(() => {
    const categories = histogram.bins.map((bin) => fmtNumber((bin.from + bin.to) / 2, 1));
    const data = histogram.bins.map((bin) => ({
      value: bin.count,
      itemStyle: { color: (bin.from + bin.to) / 2 < 0 ? palette.loss : palette.profit },
    }));
    return {
      animation: !prefersReducedMotion(),
      grid: { left: 40, right: 12, top: 12, bottom: 28 },
      xAxis: {
        type: "category",
        data: categories,
        name: "R multiple (bin centre)",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: palette.dim },
        axisLabel: { color: palette.dim, interval: Math.max(0, Math.floor(categories.length / 8) - 1) },
        axisLine: { lineStyle: { color: palette.line } },
      },
      yAxis: {
        type: "value",
        name: "Trades",
        nameTextStyle: { color: palette.dim },
        axisLabel: { color: palette.dim },
        splitLine: { lineStyle: { color: palette.line, opacity: 0.06 } },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.surface,
        borderColor: palette.line,
        textStyle: { color: palette.ink },
        extraCssText: "backdrop-filter: blur(12px); border-radius: 12px; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);",
      },
      series: [{ type: "bar", data, barCategoryGap: "10%" }],
    };
  }, [histogram, palette]);
  const ref = useChart(option);
  return (
    <div
      ref={ref}
      className="chart chart-r"
      role="img"
      aria-label={`R distribution of ${histogram.n} trades. Median ${fmtNumber(histogram.median)} R.`}
    />
  );
}
