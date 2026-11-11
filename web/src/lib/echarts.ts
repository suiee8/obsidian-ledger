// Only the chart types and components the app uses are registered. The rest of ECharts stays
// out of the bundle.
import * as echarts from "echarts/core";
import { BarChart, LineChart, RadarChart, ScatterChart } from "echarts/charts";
import {
  BrushComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  RadarChart,
  ScatterChart,
  BrushComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export { echarts };
