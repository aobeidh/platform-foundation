import { useTranslation } from 'react-i18next';
import type { Control, FieldValues, Path } from 'react-hook-form';
import type { JsonSchema } from '@/kit/api';
import { Input } from '@/ui/atoms/input';
import { Switch } from '@/ui/atoms/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/atoms/select';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/ui/atoms/form';
import { labelFor } from './schema';

/** Renders every property of a JSON Schema object as a labelled control, under a field prefix such as "config". */
export function SchemaFields<T extends FieldValues>({ schema, control, prefix }: { schema: JsonSchema; control: Control<T>; prefix: string }) {
  const { t } = useTranslation();
  const req = new Set(schema.required ?? []);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Object.entries(schema.properties ?? {}).map(([key, prop]) => {
        const name = `${prefix}.${key}` as Path<T>;
        const type = Array.isArray(prop.type) ? prop.type[0] : prop.type;
        const label = `${labelFor(key, prop)}${req.has(key) ? '' : ` (${t('plug.optional')})`}`;
        const hint = prop.description ?? (prop.minimum !== undefined && prop.maximum !== undefined ? `${prop.minimum} – ${prop.maximum}` : undefined);
        if (type === 'boolean') {
          return (
            <FormField key={key} control={control} name={name} render={({ field }) => (
              <FormItem className="flex items-center justify-between gap-4 rounded-[10px] border border-line bg-panel px-3 py-2 sm:col-span-2">
                <div><FormLabel>{label}</FormLabel>{hint && <FormDescription>{hint}</FormDescription>}</div>
                <FormControl><Switch checked={!!field.value} onCheckedChange={field.onChange} /></FormControl>
              </FormItem>
            )} />
          );
        }
        return (
          <FormField key={key} control={control} name={name} render={({ field }) => (
            <FormItem>
              <FormLabel>{label}</FormLabel>
              {prop.enum ? (
                <Select value={String(field.value ?? '')} onValueChange={field.onChange}>
                  <FormControl><SelectTrigger className="w-full"><SelectValue /></SelectTrigger></FormControl>
                  <SelectContent>{prop.enum.map((v) => <SelectItem key={String(v)} value={String(v)}>{String(v)}</SelectItem>)}</SelectContent>
                </Select>
              ) : (
                <FormControl>
                  <Input {...field} value={(field.value as string | number | undefined) ?? ''} inputMode={type === 'integer' || type === 'number' ? 'numeric' : undefined}
                    type={prop.format === 'uri' ? 'url' : 'text'} dir={prop.format === 'uri' ? 'ltr' : undefined}
                    placeholder={prop.default !== undefined ? String(prop.default) : undefined} unit={key.endsWith('_ms') ? 'ms' : undefined} />
                </FormControl>
              )}
              {hint && <FormDescription>{hint}</FormDescription>}
              <FormMessage />
            </FormItem>
          )} />
        );
      })}
    </div>
  );
}
