import { cn } from '@/lib/utils';
import { delay, useInView } from './use-width';

export interface RankedItem { id: string; name: string; subtitle?: React.ReactNode; value: number; color: string }

/** Numbered rows with a proportional bar on a track, the value and its share. Click a row to drill in. */
export function RankedBars({ items, format, onSelect, ariaLabel }: {
  items: RankedItem[]; format: (v: number) => string; onSelect?: (id: string) => void; ariaLabel: string;
}) {
  const [ref, inView] = useInView<HTMLOListElement>();
  const max = Math.max(1, ...items.map((i) => i.value));
  const total = items.reduce((s, i) => s + i.value, 0) || 1;
  return (
    <ol ref={ref} aria-label={ariaLabel} className="flex flex-col gap-1">
      {items.map((it, i) => (
        <li key={it.id} className={inView ? 'anim-fade-up' : 'anim-wait'} style={delay(i * 70)}>
          <button type="button" disabled={!onSelect} onClick={() => onSelect?.(it.id)}
            className={cn('grid w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-[10px] px-2 py-2 text-start transition',
              onSelect && 'hover:bg-panel2 focus-visible:outline-2 focus-visible:outline-accent')}>
            <span className="num text-12 text-dim">{i + 1}</span>
            <span className="min-w-0">
              <span className="block truncate text-13 font-medium text-fg">{it.name}</span>
              {it.subtitle && <span className="block truncate text-12 text-dim">{it.subtitle}</span>}
            </span>
            <span className="num text-end text-13 font-medium text-fg">{format(it.value)}<span className="ms-2 text-12 font-normal text-dim">{Math.round((100 * it.value) / total)}%</span></span>
            <span className="col-span-2 col-start-2 h-1.5 overflow-hidden rounded-full bg-panel2">
              <span className={cn('block h-full rounded-full', inView ? 'anim-grow-x' : 'anim-wait')}
                style={{ width: `${(100 * it.value) / max}%`, background: it.color, ...delay(150 + i * 70) }} />
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
