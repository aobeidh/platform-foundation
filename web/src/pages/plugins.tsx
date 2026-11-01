import { KeyRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCan, usePlugins, useRecords, type ConnectionSpec } from '@/kit/api';
import { labelFor, problemText } from '@/kit/governed';
import { Badge } from '@/ui/atoms/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/atoms/card';
import { Mono } from '@/ui/atoms/misc';
import { StyleChip } from '@/ui/atoms/style-chip';
import { ErrorState, LoadingState } from '@/ui/molecules/states';
import { PageHeader } from '@/ui/templates/page-header';
import { usePrefs } from '@/lib/prefs';
import { display, styleOf } from './shared';

export function PluginsPage() {
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const plugins = usePlugins();
  const can = useCan();
  const records = useRecords<ConnectionSpec>('connections', can('connections:read'));
  const used = (id: string, v: string) => (records.data?.items ?? []).filter((r) => r.current.spec.connector === id && r.current.spec.connector_version === v && r.status !== 'retired').length;
  return (
    <>
      <PageHeader eyebrow={t('plug.eyebrow')} title={t('plug.title')} description={t('plug.desc')} tags={['P11', 'P12', 'P38', 'F12']} />
      {plugins.isLoading ? <div className="glass"><LoadingState /></div> : plugins.error ? <div className="glass"><ErrorState cause={problemText(plugins.error)} onRetry={() => void plugins.refetch()} /></div> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {plugins.data?.items.map((p) => {
            const req = new Set(p.configSchema.required ?? []);
            return (
              <Card key={`${p.id}@${p.version}`}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">{display(p.display, lang)}<Mono>{p.id}@{p.version}</Mono></CardTitle>
                  <CardDescription>{t('plug.publisher')}: {p.publisher} · {t('plug.spi')}: <span className="font-mono">{p.spi}</span></CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone="selected">{p.kind}</Badge><StyleChip style={styleOf(p)} />
                    {p.capabilities.map((c) => <Badge key={c}>{c}</Badge>)}
                  </div>
                  {!plugins.data?.detail ? <p className="text-12 text-dim">{t('plug.withheld')}</p> : <div>
                    <div className="eyebrow mb-1.5">{t('plug.settings')}</div>
                    <ul className="divide-y divide-line rounded-[10px] border border-line">
                      {Object.entries(p.configSchema.properties ?? {}).map(([k, s]) => (
                        <li key={k} className="flex items-center justify-between gap-3 px-3 py-1.5 text-13">
                          <span className="min-w-0"><span className="text-fg">{labelFor(k, s)}</span> <span className="font-mono text-11 text-dim">{k}: {Array.isArray(s.type) ? s.type.join('|') : s.type}{s.enum ? ` (${s.enum.join(', ')})` : ''}</span></span>
                          <span className={req.has(k) ? 'text-12 font-medium text-fg' : 'text-12 text-dim'}>{t(req.has(k) ? 'plug.required' : 'plug.optional')}</span>
                        </li>
                      ))}
                    </ul>
                  </div>}
                  {!!p.secrets.length && <div className="flex flex-wrap items-center gap-1.5 text-12 text-muted"><KeyRound className="size-3.5" aria-hidden />{t('plug.secrets')}: {p.secrets.map((s) => <Mono key={s}>{s}</Mono>)}</div>}
                  {records.data && <p className="text-12 text-dim">{t('plug.used', { n: used(p.id, p.version) })}</p>}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
