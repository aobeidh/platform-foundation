import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { ChartContainer, ChartLegendContent, EChart, useChart, type ChartConfig } from './echart';
import { baseOption, categoryAxis, useChartTheme, valueAxis, withAlpha } from './theme';
import { tooltipBase, tooltipHtml } from './tooltip';

export interface AreaChartProps<T> {
  data: T[]; xKey: keyof T & string; config: ChartConfig; stacked?: boolean;
  valueFormatter?: (v: number) => string; /** Counts: ticks at whole numbers only. */ integer?: boolean; xFormatter?: (v: string) => string; ariaLabel: string; height?: number;
}

function Inner<T>({ data, xKey, stacked, valueFormatter = String, xFormatter = (v) => v, ariaLabel, height, integer }: Omit<AreaChartProps<T>, 'config'>) {
  const t = useChartTheme();
  const { config, hidden } = useChart();
  const option = useMemo<EChartsOption>(() => {
    const keys = Object.keys(config).filter((k) => !hidden.has(k));
    return {
      ...baseOption(t),
      tooltip: { ...tooltipBase, trigger: 'axis', formatter: (p: unknown) => tooltipHtml(p as never, config, valueFormatter) },
      xAxis: categoryAxis(t, data.map((d) => xFormatter(String(d[xKey])))),
      yAxis: valueAxis(t, valueFormatter, { splitNumber: 4, minInterval: integer ? 1 : undefined }),
      series: keys.map((k, i) => {
        const c = t.resolve(config[k].color ?? 'var(--accent)');
        return {
          id: k, name: String(k), type: 'line', smooth: 0.35, showSymbol: false, stack: stacked ? 'total' : undefined,
          lineStyle: { width: 2, color: c }, itemStyle: { color: c },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
            { offset: 0, color: withAlpha(c, 0.35) }, { offset: 1, color: withAlpha(c, 0.05) }] } },
          emphasis: { focus: 'series' }, animationDelay: (idx: number) => idx * 12 + i * 80,
          data: data.map((d) => Number((d as Record<string, unknown>)[k] ?? 0)),
        };
      }),
    } as EChartsOption;
  }, [integer, t, config, hidden, data, xKey, stacked, valueFormatter, xFormatter]);
  return <EChart option={option} ariaLabel={ariaLabel} height={height} />;
}

export function AreaChart<T>({ config, ...rest }: AreaChartProps<T>) {
  return (
    <ChartContainer config={config}>
      <ChartLegendContent />
      <Inner {...rest} />
    </ChartContainer>
  );
}
