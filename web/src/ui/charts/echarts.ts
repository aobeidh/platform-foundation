import * as echarts from 'echarts/core';
import { BarChart, HeatmapChart, LineChart, PieChart } from 'echarts/charts';
import { AriaComponent, DatasetComponent, GridComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

// Tree-shaken: only these modules are bundled. Legends are HTML and the donut centre is an HTML overlay.
echarts.use([LineChart, BarChart, PieChart, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent,
  MarkLineComponent, DatasetComponent, AriaComponent, CanvasRenderer]);

export { echarts };
