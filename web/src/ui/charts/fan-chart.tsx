import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { ChartContainer, ChartLegendContent, EChart, type ChartConfig } from './echart';
import { baseOption, categoryAxis, useChartTheme, valueAxis, withAlpha } from './theme';
import { tooltipBase, tooltipHtml } from './tooltip';

export interface FanRow { x: string; actual?: number; forecast?: number; low?: number; high?: number }

export interface FanChartProps {
  data: FanRow[]; config: ChartConfig; budget?: number; budgetLabel: string;
  valueFormatter?: (v: number) => string; ariaLabel: string; height?: number;
}

/** Actuals solid, forecast dashed from the last actual, an 80% band as two stacked helper lines, and a limit line. */
export function FanChart({ data, config, budget, budgetLabel, valueFormatter = String, ariaLabel, height = 240 }: FanChartProps) {
  const t = useChartTheme();
  const option = useMemo<EChartsOption>(() => {
    const fc = t.forecast;
    const band = withAlpha(fc, 0.15);
    const actual = t.resolve(config.actual?.color ?? 'var(--accent)');
    return {
      ...baseOption(t),
      tooltip: { ...tooltipBase, trigger: 'axis', formatter: (p: unknown) => tooltipHtml(p as never, config, valueFormatter) },
      xAxis: categoryAxis(t, data.map((d) => d.x)),
      yAxis: valueAxis(t, valueFormatter, { min: (v: { min: number }) => Math.floor(v.min * 0.9), splitNumber: 4 }),
      series: [
        { id: '_low', type: 'line', stack: 'band', symbol: 'none', lineStyle: { opacity: 0 }, data: data.map((d) => d.low ?? null), animationDelay: 700 },
        { id: '_high', type: 'line', stack: 'band', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: band },
          data: data.map((d) => (d.high != null && d.low != null ? d.high - d.low : null)), animationDelay: 700 },
        { id: 'actual', type: 'line', smooth: 0.3, showSymbol: false, lineStyle: { width: 2, color: actual }, itemStyle: { color: actual },
          data: data.map((d) => d.actual ?? null),
          markLine: budget ? { symbol: 'none', silent: true, lineStyle: { color: t.bad, type: 'dashed', width: 1 },
            label: { position: 'insideEndTop', color: t.bad, fontSize: 11, formatter: budgetLabel }, data: [{ yAxis: budget }] } : undefined },
        { id: 'forecast', type: 'line', smooth: 0.3, showSymbol: false, lineStyle: { width: 2, type: 'dashed', color: fc }, itemStyle: { color: fc },
          data: data.map((d) => d.forecast ?? null), animationDelay: 600 },
      ],
    } as EChartsOption;
  }, [t, data, config, budget, budgetLabel, valueFormatter]);
  return (
    <ChartContainer config={config}>
      <ChartLegendContent keys={['actual', 'forecast']} />
      <EChart option={option} ariaLabel={ariaLabel} height={height} />
    </ChartContainer>
  );
}
