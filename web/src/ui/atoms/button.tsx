import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-[10px] font-medium transition duration-150 active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-accent text-on-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:brightness-110',
        accent: 'bg-gradient-to-r from-accent to-accent2 text-on-accent hover:brightness-110',
        secondary: 'border border-line2 bg-panel text-fg hover:bg-panel2',
        outline: 'border border-line2 bg-transparent text-fg hover:bg-panel2',
        ghost: 'text-muted hover:bg-panel2 hover:text-fg',
        destructive: 'bg-[#be123c] text-white hover:bg-[#9f1239]',
        link: 'h-auto px-0 text-accent underline-offset-4 hover:underline',
      },
      size: {
        xs: 'h-7 px-2.5 text-12',
        sm: 'h-8 px-3 text-13',
        default: 'h-9 px-3.5 text-[13.5px]',
        lg: 'h-10 px-4 text-14',
        icon: 'size-9',
        'icon-sm': 'size-8',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps extends React.ComponentProps<'button'>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Shows a spinner and disables the button. Pass the verb in progress as the children, e.g. "Saving". */
  loading?: boolean;
}

function Button({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : 'button';
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {asChild ? children : (<>{loading && <Loader2 className="animate-spin" aria-hidden />}{children}</>)}
    </Comp>
  );
}

export { Button, buttonVariants };
