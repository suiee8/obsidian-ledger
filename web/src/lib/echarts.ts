// Only the chart types and components the app uses are registered. The rest of ECharts stays
// out of the bundle.
import * as echarts from "echarts/core";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  BrushComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  BrushComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export { echarts };
