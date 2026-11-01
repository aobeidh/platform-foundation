import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

/** A change with an arrow and a sign. `goodWhen` says which direction is good for this measure. */
export function Delta({ value, format, goodWhen = 'up', className }: {
  value: number; format: (v: number) => string; goodWhen?: 'up' | 'down'; className?: string;
}) {
  const flat = Math.abs(value) < 1e-9;
  const good = flat ? null : (value > 0) === (goodWhen === 'up');
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn('num inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-12 font-medium',
      good === null ? 'bg-panel2 text-muted' : good ? 'bg-good/12 text-good' : 'bg-bad/12 text-bad', className)}>
      <Icon aria-hidden className="size-3 rtl:-scale-x-100" />
      {value > 0 ? '+' : value < 0 ? '−' : ''}{format(Math.abs(value))}
    </span>
  );
}

export function CountBadge({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <span className={cn('num inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold leading-none text-on-accent', className)}>
      {count > 99 ? '99+' : count}
    </span>
  );
}

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return <kbd className={cn('inline-flex h-5 items-center rounded-[6px] border border-line2 bg-panel2 px-1.5 font-mono text-11 text-muted', className)}>{children}</kbd>;
}

export function Dot({ className }: { className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2 rounded-full', className)} />;
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <code className={cn('rounded-[6px] bg-panel2 px-1.5 py-0.5 font-mono text-12 text-muted', className)}>{children}</code>;
}
