import * as React from 'react';
import { cn } from '@/lib/utils';

export const fieldBase =
  'h-9 w-full min-w-0 rounded-[10px] border border-line2 bg-panel px-3 text-13 text-fg outline-none transition placeholder:text-dim focus-visible:border-accent focus-visible:shadow-(--shadow-glow) disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-bad aria-invalid:focus-visible:shadow-none';

export interface InputProps extends React.ComponentProps<'input'> {
  /** Leading icon, drawn inside the field at the start edge. */
  icon?: React.ReactNode;
  /** Trailing unit, such as "ms" or "%". */
  unit?: string;
}

function Input({ className, type, icon, unit, ...props }: InputProps) {
  const field = (
    <input type={type} data-slot="input" className={cn(fieldBase, icon && 'ps-8', unit && 'pe-10', className)} {...props} />
  );
  if (!icon && !unit) return field;
  return (
    <div className="relative w-full">
      {icon && <span aria-hidden className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-dim [&_svg]:size-4">{icon}</span>}
      {field}
      {unit && <span aria-hidden className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-12 text-dim">{unit}</span>}
    </div>
  );
}

export { Input };
