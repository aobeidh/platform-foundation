import * as React from 'react';
import { cn } from '@/lib/utils';
import { fieldBase } from './input';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea data-slot="textarea" className={cn(fieldBase, 'min-h-20 py-2 leading-5', className)} {...props} />;
}

export { Textarea };
