import type { Control, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/ui/atoms/form';

/** Label above, then the control, then the hint or the error (never both). react-hook-form wires the ARIA. */
export function FieldRow<T extends FieldValues, N extends FieldPath<T>>({ control, name, label, hint, children, className }: {
  control: Control<T>; name: N; label: React.ReactNode; hint?: React.ReactNode; className?: string;
  children: (field: ControllerRenderProps<T, N>) => React.ReactElement;
}) {
  return (
    <FormField control={control} name={name} render={({ field }) => (
      <FormItem className={className}>
        <FormLabel>{label}</FormLabel>
        <FormControl>{children(field)}</FormControl>
        {hint && <FormDescription>{hint}</FormDescription>}
        <FormMessage />
      </FormItem>
    )} />
  );
}

/** A labelled row for controls that sit beside their label (switches, checkboxes). */
export function InlineField({ id, label, hint, control }: { id: string; label: React.ReactNode; hint?: React.ReactNode; control: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-[10px] border border-line bg-panel px-3 py-2.5">
      <div className="min-w-0">
        <label htmlFor={id} className="text-13 font-medium text-fg">{label}</label>
        {hint && <p id={`${id}-hint`} className="text-12 text-dim">{hint}</p>}
      </div>
      {control}
    </div>
  );
}
