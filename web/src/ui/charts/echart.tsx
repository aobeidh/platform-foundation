import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { cn } from '@/lib/utils';
import { echarts } from './echarts';

export type ChartConfig = Record<string, { label: React.ReactNode; color?: string; icon?: React.ComponentType }>;

interface Ctx { config: ChartConfig; hidden: Set<string>; toggle: (key: string) => void }
const ChartCtx = createContext<Ctx | null>(null);

export function useChart() {
  const v = useContext(ChartCtx);
  if (!v) throw new Error('chart components must sit inside ChartContainer');
  return v;
}

/** Writes --color-<key> for each series and holds the legend's hidden set, like shadcn's chart container. */
export function ChartContainer({ config, className, children }: { config: ChartConfig; className?: string; children: React.ReactNode }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const style = useMemo(() => Object.fromEntries(Object.entries(config).filter(([, v]) => v.color).map(([k, v]) => [`--color-${k}`, v.color])), [config]);
  const value = useMemo<Ctx>(() => ({ config, hidden, toggle: (key) => setHidden((h) => { const n = new Set(h); if (n.has(key)) n.delete(key); else n.add(key); return n; }) }), [config, hidden]);
  return (
    <ChartCtx.Provider value={value}>
      <div data-slot="chart" style={style as React.CSSProperties} className={cn('flex min-w-0 flex-col gap-2', className)}>{children}</div>
    </ChartCtx.Provider>
  );
}

/** HTML legend at the top start; clicking an item hides or shows its series. */
export function ChartLegendContent({ keys, className }: { keys?: string[]; className?: string }) {
  const { config, hidden, toggle } = useChart();
  const list = keys ?? Object.keys(config);
  if (list.length < 2) return null;
  return (
    <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-1', className)}>
      {list.map((k) => (
        <button key={k} type="button" onClick={() => toggle(k)} aria-pressed={!hidden.has(k)}
          className={cn('inline-flex items-center gap-1.5 rounded-[6px] text-12 text-muted transition hover:text-fg focus-visible:outline-2 focus-visible:outline-accent', hidden.has(k) && 'opacity-45 line-through')}>
          <span aria-hidden className="size-2 rounded-full" style={{ background: `var(--color-${k})` }} />
          {config[k]?.label}
        </button>
      ))}
    </div>
  );
}

/**
 * The only component that calls echarts.init. The first option is applied when the chart is a quarter in view, so
 * the entry animation is seen; later options merge by series id, so theme or language changes transition.
 */
export function EChart({ option, ariaLabel, className, height = 240 }: { option: EChartsOption; ariaLabel: string; className?: string; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const inst = useRef<ReturnType<typeof echarts.init> | null>(null);
  const applied = useRef(false);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    if (!el.current) return;
    const chart = echarts.init(el.current, undefined, { renderer: 'canvas', devicePixelRatio: window.devicePixelRatio });
    inst.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el.current);
    let io: IntersectionObserver | undefined;
    if ('IntersectionObserver' in window) {
      io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setInView(true); io?.disconnect(); } }, { threshold: 0.25 });
      io.observe(el.current);
    } else setInView(true);
    return () => { io?.disconnect(); ro.disconnect(); chart.dispose(); inst.current = null; applied.current = false; };
  }, []);

  useEffect(() => {
    const chart = inst.current;
    if (!chart || !inView) return;
    if (!applied.current) { chart.setOption(option, { notMerge: true }); applied.current = true; }
    else chart.setOption(option, { replaceMerge: ['series'] });
  }, [option, inView]);

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={el} role="img" aria-label={ariaLabel} className={cn('absolute inset-0', className)} />
    </div>
  );
}
