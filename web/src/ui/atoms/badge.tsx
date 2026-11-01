import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-12 font-medium [&>svg]:size-3',
  {
    variants: {
      tone: {
        neutral: 'border-line2 bg-panel2 text-muted',
        selected: 'border-accent/30 bg-accent/12 text-accent',
        good: 'border-good/30 bg-good/12 text-good',
        warn: 'border-warn/30 bg-warn/12 text-warn',
        bad: 'border-bad/30 bg-bad/12 text-bad',
        info: 'border-info/30 bg-info/12 text-info',
        forecast: 'border-forecast/30 bg-forecast/12 text-forecast',
        money: 'border-money/30 bg-money/12 text-money',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export type Tone = NonNullable<VariantProps<typeof badgeVariants>['tone']>;

export interface BadgeProps extends React.ComponentProps<'span'>, VariantProps<typeof badgeVariants> {
  /** A 6 px leading dot in the tone colour. */
  dot?: boolean;
}

function Badge({ className, tone, dot, children, ...props }: BadgeProps) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ tone }), className)} {...props}>
      {dot && <span aria-hidden className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export { Badge, badgeVariants };
