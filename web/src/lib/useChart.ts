import { useEffect, useRef } from "react";
import { echarts } from "./echarts";
import type { EChartsOption } from "echarts";

/**
 * Creates one ECharts instance per element, updates it when the option changes, resizes it with
 * its container, and disposes it on unmount. `onChart` receives the instance after it is created
 * and null when it is disposed, for charts that need events such as brushing.
 */
export function useChart(option: EChartsOption, onChart?: (chart: echarts.ECharts | null) => void) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onChartRef = useRef(onChart);
  onChartRef.current = onChart;

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const chart = echarts.init(element, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    onChartRef.current?.(chart);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    return () => {
      observer.disconnect();
      onChartRef.current?.(null);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return ref;
}