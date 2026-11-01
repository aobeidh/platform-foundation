import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { ChartContainer, EChart, type ChartConfig } from './echart';
import { baseOption, useChartTheme } from './theme';
import { tooltipBase } from './tooltip';

export interface HeatmapChartProps {
  xLabels: string[]; yLabels: string[]; cells: [x: number, y: number, value: number][];
  valueLabel: string; valueFormatter?: (v: number) => string; ariaLabel: string; height?: number;
}

export function HeatmapChart({ xLabels, yLabels, cells, valueLabel, valueFormatter = String, ariaLabel, height = 220 }: HeatmapChartProps) {
  const t = useChartTheme();
  const config: ChartConfig = { value: { label: valueLabel, color: 'var(--accent)' } };
  const option = useMemo<EChartsOption>(() => {
    const max = Math.max(1, ...cells.map((c) => c[2]));
    const accent = t.accent;
    return {
      ...baseOption(t),
      grid: { left: 8, right: 8, top: 8, bottom: 4, containLabel: true },
      tooltip: { ...tooltipBase, formatter: (p: unknown) => {
        const v = (p as { value: [number, number, number] }).value;
        return `<div class="glass-strong rounded-[10px] px-2.5 py-2 text-12"><div class="mb-1 font-medium text-fg">${yLabels[v[1]]} · ${xLabels[v[0]]}</div><div class="flex gap-4"><span class="text-muted">${valueLabel}</span><span class="num ms-auto font-medium text-fg">${valueFormatter(v[2])}</span></div></div>`;
      } },
      xAxis: { type: 'category', data: xLabels, inverse: t.isRtl, splitArea: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.dim, fontSize: 11, interval: 2 } },
      yAxis: { type: 'category', data: yLabels, position: t.isRtl ? 'right' : 'left', axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.dim, fontSize: 11 } },
      visualMap: { show: false, min: 0, max, inRange: { color: [t.panel2, t.resolve('color-mix(in oklab, var(--accent) 45%, var(--panel-strong))'), accent] } },
      series: [{ id: 'value', type: 'heatmap', data: cells, itemStyle: { borderColor: t.card, borderWidth: 2, borderRadius: 3 },
        animationDelay: (i: number) => i * 6, emphasis: { itemStyle: { borderColor: accent } } }],
    } as EChartsOption;
  }, [t, xLabels, yLabels, cells, valueLabel, valueFormatter]);
  return <ChartContainer config={config}><EChart option={option} ariaLabel={ariaLabel} height={height} /></ChartContainer>;
}
