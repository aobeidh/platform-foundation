import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { ChartContainer, EChart, useChart, type ChartConfig } from './echart';
import { baseOption, useChartTheme } from './theme';
import { tooltipBase, tooltipHtml } from './tooltip';

export interface DonutChartProps<T> {
  data: T[]; nameKey: keyof T & string; valueKey: keyof T & string; config: ChartConfig;
  centerLabel: string; centerValue?: string; valueFormatter?: (v: number) => string; ariaLabel: string; height?: number; otherLabel?: string;
}

function Inner<T>({ data, nameKey, valueKey, centerLabel, centerValue, valueFormatter = String, ariaLabel, height = 220, otherLabel = 'Other' }: Omit<DonutChartProps<T>, 'config'>) {
  const t = useChartTheme();
  const { config, hidden, toggle } = useChart();
  const slices = useMemo(() => {
    const rows = data.map((d) => ({ key: String(d[nameKey]), value: Number(d[valueKey]) })).filter((r) => r.value > 0).sort((a, b) => b.value - a.value);
    if (rows.length <= 5) return rows;
    return [...rows.slice(0, 4), { key: '_other', value: rows.slice(4).reduce((s, r) => s + r.value, 0) }];
  }, [data, nameKey, valueKey]);
  const total = slices.filter((s) => !hidden.has(s.key)).reduce((s, r) => s + r.value, 0);
  const option = useMemo<EChartsOption>(() => ({
    ...baseOption(t),
    tooltip: { ...tooltipBase, trigger: 'item', formatter: (p: unknown) => tooltipHtml({ ...(p as object), seriesId: undefined } as never, config, valueFormatter, '') },
    series: [{
      id: 'donut', type: 'pie', radius: ['62%', '82%'], padAngle: 2, itemStyle: { borderRadius: 4 }, label: { show: false },
      animationType: 'expansion', animationDuration: 1000, animationEasing: 'cubicOut',
      data: slices.filter((s) => !hidden.has(s.key)).map((s) => ({ name: s.key === '_other' ? otherLabel : String(config[s.key]?.label ?? s.key), value: s.value,
        itemStyle: { color: t.resolve(s.key === '_other' ? 'var(--line-strong)' : config[s.key]?.color ?? 'var(--accent)') } })),
    }],
  }) as EChartsOption, [t, slices, hidden, config, valueFormatter, otherLabel]);
  return (
    <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="relative">
        <EChart option={option} ariaLabel={ariaLabel} height={height} />
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div><div className="num text-22 font-semibold text-fg">{centerValue ?? valueFormatter(total)}</div><div className="text-12 text-dim">{centerLabel}</div></div>
        </div>
      </div>
      <ul className="flex flex-col gap-1.5">
        {slices.map((s) => (
          <li key={s.key}>
            <button type="button" onClick={() => toggle(s.key)} aria-pressed={!hidden.has(s.key)}
              className="flex w-full items-center gap-2 rounded-[8px] px-1.5 py-1 text-13 transition hover:bg-panel2 aria-[pressed=false]:opacity-45">
              <span aria-hidden className="size-2 rounded-full" style={{ background: s.key === '_other' ? 'var(--line-strong)' : `var(--color-${s.key})` }} />
              <span className="truncate text-muted">{s.key === '_other' ? otherLabel : config[s.key]?.label}</span>
              <span className="num ms-auto font-medium text-fg">{valueFormatter(s.value)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DonutChart<T>({ config, ...rest }: DonutChartProps<T>) {
  return <ChartContainer config={config}><Inner {...rest} /></ChartContainer>;
}
