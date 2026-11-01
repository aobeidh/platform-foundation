import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { usePlugins, useSaveDraft, type Connection, type ConnectionSpec } from '@/kit/api';
import { ProblemAlert, SchemaFields, clean, defaults, objectToZod } from '@/kit/governed';
import { Button } from '@/ui/atoms/button';
import { Form } from '@/ui/atoms/form';
import { Input } from '@/ui/atoms/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/atoms/select';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/ui/atoms/sheet';
import { FieldRow } from '@/ui/molecules/form-field';
import { usePrefs } from '@/lib/prefs';
import { display } from './shared';

/**
 * Create a draft, or edit one. The connector settings are rendered from the plugin's own configuration schema
 * (/portal/plugins), so a new connector plugin needs no portal change.
 */
export function ConnectionForm({ open, onOpenChange, record, onSaved }: {
  open: boolean; onOpenChange: (o: boolean) => void; record?: Connection; onSaved: (c: Connection) => void;
}) {
  const { t } = useTranslation();
  const { lang, dir } = usePrefs();
  const plugins = usePlugins();
  const save = useSaveDraft<ConnectionSpec>('connections');
  const connectors = useMemo(() => plugins.data?.items.filter((p) => p.kind === 'connector') ?? [], [plugins.data]);
  const initial = record?.current.spec;
  const [pluginKey, setPluginKey] = useState(initial ? `${initial.connector}@${initial.connector_version}` : '');
  const plugin = connectors.find((p) => `${p.id}@${p.version}` === pluginKey);

  const schema = useMemo(() => z.object({
    name: z.string().trim().min(1, 'form.err.required').max(80, `form.err.max|${JSON.stringify({ n: 80 })}`),
    connector: z.string().min(1, 'form.err.choose'),
    config: plugin ? objectToZod(plugin.configSchema) : z.object({}).passthrough(),
  }), [plugin]);
  type Values = z.infer<typeof schema>;

  const form = useForm<Values>({ resolver: zodResolver(schema), mode: 'onChange',
    defaultValues: { name: initial?.name ?? '', connector: pluginKey, config: (initial?.config ?? {}) as Values['config'] } });

  useEffect(() => {
    if (!open) return;
    const key = initial ? `${initial.connector}@${initial.connector_version}` : connectors[0] ? `${connectors[0].id}@${connectors[0].version}` : '';
    setPluginKey(key);
    const p = connectors.find((x) => `${x.id}@${x.version}` === key);
    form.reset({ name: initial?.name ?? '', connector: key, config: { ...(p ? defaults(p.configSchema) : {}), ...(initial?.config ?? {}) } as Values['config'] });
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, record?.id, connectors.length]);

  const choose = (key: string) => {
    setPluginKey(key);
    const p = connectors.find((x) => `${x.id}@${x.version}` === key);
    form.setValue('connector', key, { shouldValidate: true });
    form.setValue('config', (p ? defaults(p.configSchema) : {}) as Values['config']);
  };

  const submit = form.handleSubmit((v) => {
    if (!plugin) return;
    const spec: ConnectionSpec = { name: v.name.trim(), connector: plugin.id, connector_version: plugin.version, config: clean(plugin.configSchema, v.config as Record<string, unknown>) };
    save.mutate({ id: record?.id, spec, revision: record?.revision }, { onSuccess: (c) => { onOpenChange(false); onSaved(c); } });
  });

  const editingActive = record && !['draft', 'tested'].includes(record.current.status);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={dir === 'rtl' ? 'left' : 'right'} className="glass-strong w-full max-w-xl gap-0 overflow-y-auto rounded-none p-0 sm:max-w-xl">
        <Form {...form}>
          <form onSubmit={submit} className="flex min-h-full flex-col" noValidate>
            <SheetHeader className="border-b border-line p-5">
              <SheetTitle className="text-20">{!record ? t('conn.form.create') : editingActive ? t('conn.form.editActive') : t('conn.form.edit')}</SheetTitle>
              <SheetDescription>{editingActive ? t('conn.form.editActiveHint', { v: record.activeVersion }) : t('conn.form.desc')}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-1 flex-col gap-5 p-5">
              <FieldRow control={form.control} name="name" label={t('conn.form.name')} hint={t('conn.form.nameHint')}>
                {(f) => <Input {...f} autoComplete="off" />}
              </FieldRow>
              <FieldRow control={form.control} name="connector" label={t('conn.form.connector')} hint={t('conn.form.connectorHint')}>
                {(f) => (
                  <Select value={f.value} onValueChange={choose} disabled={!!record}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>{connectors.map((p) => (
                      <SelectItem key={`${p.id}@${p.version}`} value={`${p.id}@${p.version}`}>{display(p.display, lang)} <span className="font-mono text-12 text-dim">{p.id}@{p.version}</span></SelectItem>
                    ))}</SelectContent>
                  </Select>
                )}
              </FieldRow>
              {plugin && (
                <fieldset className="rounded-[12px] border border-line p-4">
                  <legend className="px-1 text-13 font-semibold text-fg">{t('conn.form.settings')} · <span className="font-mono text-12 font-normal text-dim">{plugin.id}@{plugin.version}</span></legend>
                  <SchemaFields schema={plugin.configSchema} control={form.control} prefix="config" />
                </fieldset>
              )}
              {save.error && <ProblemAlert error={save.error} />}
              {form.formState.submitCount > 0 && !form.formState.isValid && <p role="status" className="text-13 text-bad">{t('conn.form.fix')}</p>}
            </div>
            <SheetFooter className="flex-row justify-end gap-2 border-t border-line p-4">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t('common.cancel')}</Button>
              <Button type="submit" loading={save.isPending}>{save.isPending ? t('common.saving') : record ? t('conn.form.save.go') : t('conn.form.create.go')}</Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
