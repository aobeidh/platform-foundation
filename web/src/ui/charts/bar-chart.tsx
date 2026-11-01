import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { ChartContainer, ChartLegendContent, EChart, useChart, type ChartConfig } from './echart';
import { baseOption, categoryAxis, useChartTheme, valueAxis } from './theme';
import { tooltipBase, tooltipHtml } from './tooltip';

export interface BarChartProps<T> {
  data: T[]; xKey: keyof T & string; config: ChartConfig; layout?: 'vertical' | 'horizontal';
  /** Colour each bar by a CSS colour from the row instead of by series (for bars that mean statuses). */
  colorKey?: keyof T & string; valueFormatter?: (v: number) => string; /** Counts: ticks at whole numbers only. */ integer?: boolean; ariaLabel: string; height?: number;
}

function Inner<T>({ data, xKey, layout = 'vertical', colorKey, valueFormatter = String, ariaLabel, height, integer }: Omit<BarChartProps<T>, 'config'>) {
  const t = useChartTheme();
  const { config, hidden } = useChart();
  const option = useMemo<EChartsOption>(() => {
    const keys = Object.keys(config).filter((k) => !hidden.has(k));
    const cats = data.map((d) => String(d[xKey]));
    const horizontal = layout === 'horizontal';
    const cat = { ...categoryAxis(t, cats, { boundaryGap: true }), inverse: horizontal ? true : t.isRtl };
    const val = valueAxis(t, valueFormatter, horizontal ? { minInterval: integer ? 1 : undefined, splitNumber: 3, axisLabel: { color: t.dim, fontSize: 11, hideOverlap: true, formatter: (v: number) => valueFormatter(v) }, inverse: t.isRtl } : { splitNumber: 4, minInterval: integer ? 1 : undefined });
    const radius = horizontal ? (t.isRtl ? [4, 0, 0, 4] : [0, 4, 4, 0]) : [4, 4, 0, 0];
    return {
      ...baseOption(t),
      grid: { left: 8, right: 22, top: 12, bottom: 4, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.resolve('var(--wash)') } },
        formatter: (p: unknown) => tooltipHtml(p as never, config, valueFormatter) },
      xAxis: horizontal ? val : cat,
      yAxis: horizontal ? { ...cat, position: t.isRtl ? 'right' : 'left' } : val,
      series: keys.map((k) => ({
        id: k, type: 'bar', barWidth: 14, barGap: '30%',
        itemStyle: { borderRadius: radius, color: t.resolve(config[k].color ?? 'var(--accent)') },
        animationDelay: (i: number) => i * 70,
        data: data.map((d) => {
          const v = Number((d as Record<string, unknown>)[k] ?? 0);
          return colorKey ? { value: v, itemStyle: { color: t.resolve(String(d[colorKey])), borderRadius: radius } } : v;
        }),
      })),
    } as EChartsOption;
  }, [integer, t, config, hidden, data, xKey, layout, colorKey, valueFormatter]);
  return <EChart option={option} ariaLabel={ariaLabel} height={height} />;
}

export function BarChart<T>({ config, ...rest }: BarChartProps<T>) {
  return (
    <ChartContainer config={config}>
      <ChartLegendContent />
      <Inner {...rest} />
    </ChartContainer>
  );
}
