import { ToggleGroup as TG } from 'radix-ui';
import { cn } from '@/lib/utils';

export interface SegmentedOption<T extends string> { value: T; label: React.ReactNode; icon?: React.ReactNode }

export interface SegmentedProps<T extends string> {
  value: T;
  onValueChange: (value: T) => void;
  options: SegmentedOption<T>[];
  ariaLabel: string;
  size?: 'sm' | 'default';
  className?: string;
}

/** A single-choice control: a panel track with a raised thumb on the selected option. */
export function Segmented<T extends string>({ value, onValueChange, options, ariaLabel, size = 'default', className }: SegmentedProps<T>) {
  return (
    <TG.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onValueChange(v as T)}
      aria-label={ariaLabel}
      className={cn('inline-flex items-center gap-0.5 rounded-[10px] border border-line bg-panel2 p-0.5', className)}
    >
      {options.map((o) => (
        <TG.Item
          key={o.value}
          value={o.value}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-[8px] px-2.5 font-medium text-muted transition duration-150 hover:text-fg focus-visible:outline-2 focus-visible:outline-accent [&_svg]:size-3.5',
            size === 'sm' ? 'h-6 text-12' : 'h-7 text-13',
            'data-[state=on]:bg-card data-[state=on]:text-fg data-[state=on]:shadow-(--shadow-card)',
          )}
        >
          {o.icon}
          {o.label}
        </TG.Item>
      ))}
    </TG.Root>
  );
}
