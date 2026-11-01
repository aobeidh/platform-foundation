import { Delta } from '@/ui/atoms/misc';
import { Skeleton } from '@/ui/atoms/skeleton';
import { Sparkline } from '@/ui/charts/sparkline';
import { cn } from '@/lib/utils';

export interface KpiTileProps {
  label: string; value: string; hint: string;
  delta?: { value: number; format: (v: number) => string; goodWhen?: 'up' | 'down' };
  trend?: number[]; tone?: 'accent' | 'good' | 'bad' | 'warn' | 'info';
  onOpen?: () => void; loading?: boolean;
}

/** A value, a change with a direction, a hint that gives it scale, and a trend line in normal flow below. */
export function KpiTile({ label, value, hint, delta, trend, tone = 'accent', onOpen, loading }: KpiTileProps) {
  if (loading) {
    return (
      <div className="glass flex min-h-[124px] flex-col gap-3 p-4" aria-busy>
        <Skeleton className="h-4 w-28" /><Skeleton className="h-7 w-20" /><Skeleton className="h-3 w-36" />
      </div>
    );
  }
  return (
    <button type="button" onClick={onOpen} disabled={!onOpen}
      className={cn('glass flex min-h-[124px] w-full flex-col gap-1 p-4 text-start transition duration-150',
        onOpen && 'hover:-translate-y-px hover:border-line2 focus-visible:outline-2 focus-visible:outline-accent')}>
      <span className="text-13 font-medium text-muted">{label}</span>
      <span className="num text-28 font-semibold leading-9 text-fg">{value}</span>
      <span className="flex flex-wrap items-center gap-2 text-12 text-dim">
        {delta && <Delta {...delta} />}
        <span>{hint}</span>
      </span>
      {trend && trend.length > 1 && <span className="mt-1 block w-1/2"><Sparkline data={trend} tone={tone} ariaLabel={`${label}: trend`} /></span>}
    </button>
  );
}
