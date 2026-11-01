import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from './echart';
import { useChartTheme, withAlpha } from './theme';

const TONE: Record<string, string> = { accent: 'var(--accent)', good: 'var(--good)', bad: 'var(--bad)', warn: 'var(--warn)', info: 'var(--info)' };

/** A trend line with a soft area: no axes, no tooltip. Draws in once, like the other charts. */
export function Sparkline({ data, tone = 'accent', ariaLabel, height = 28 }: { data: number[]; tone?: keyof typeof TONE; ariaLabel: string; height?: number }) {
  const t = useChartTheme();
  const option = useMemo<EChartsOption>(() => {
    const c = t.resolve(TONE[tone]);
    return {
      animation: !t.reducedMotion, animationDuration: 900, animationEasing: 'cubicOut', animationDurationUpdate: 450,
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: data.map((_, i) => i), inverse: t.isRtl, boundaryGap: false },
      yAxis: { type: 'value', show: false, min: (v: { min: number; max: number }) => v.min - (v.max - v.min) * 0.15 },
      series: [{ id: 'spark', type: 'line', smooth: 0.4, symbol: 'none', data, lineStyle: { width: 1.6, color: c },
        areaStyle: { color: withAlpha(c, 0.12) } }],
    } as EChartsOption;
  }, [t, data, tone]);
  return <EChart option={option} ariaLabel={ariaLabel} height={height} />;
}
