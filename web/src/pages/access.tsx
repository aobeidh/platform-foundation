import { useTranslation } from 'react-i18next';
import { useApi, useMe } from '@/kit/api';
import { problemText } from '@/kit/governed';
import { Badge } from '@/ui/atoms/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/atoms/card';
import { Mono } from '@/ui/atoms/misc';
import { ErrorState, LoadingState } from '@/ui/molecules/states';
import { PageHeader } from '@/ui/templates/page-header';
import { usePrefs } from '@/lib/prefs';
import { display } from './shared';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-3 border-b border-line py-2 text-13 last:border-0"><dt className="text-muted">{label}</dt><dd className="flex flex-wrap gap-1.5 text-fg">{children}</dd></div>;
}

export function AccessPage() {
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const me = useMe();
  const { identities, identity, setIdentity } = useApi();
  if (me.isLoading) return <div className="glass"><LoadingState /></div>;
  if (me.error || !me.data) return <div className="glass"><ErrorState cause={problemText(me.error)} onRetry={() => void me.refetch()} /></div>;
  const m = me.data;
  return (
    <>
      <PageHeader eyebrow={t('acc.eyebrow')} title={t('acc.title')} description={t('acc.desc')} tags={['P21', 'P22', 'P36', 'F23']} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>{m.subject}</CardTitle><CardDescription>{m.service}</CardDescription></CardHeader>
          <CardContent><dl>
            <Row label={t('acc.subject')}><Mono>{m.subject}</Mono></Row>
            <Row label={t('acc.roles')}>{m.roles.map((r) => <Badge key={r}>{t(`role.${r}`, { defaultValue: r })}</Badge>)}</Row>
            <Row label={t('acc.scope')}>{m.platformScope ? <Badge tone="forecast">{t('shell.platformScope')}</Badge> : <Badge tone="info">{t('shell.tenant')} {m.tenant}</Badge>}</Row>
            <Row label={t('acc.caps')}>{m.capabilities.length ? m.capabilities.map((c) => <Badge key={c.name} tone="good" title={c.name}>{display(c.display, lang)}</Badge>) : <span className="text-muted">{t('common.none')}</span>}</Row>
          </dl></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t('acc.simulated')}</CardTitle><CardDescription>{t('acc.simulatedHint')}</CardDescription></CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">{m.simulated.length ? m.simulated.map((s) => <Badge key={s} tone="warn" dot>{s}</Badge>) : <span className="text-13 text-muted">{t('common.none')}</span>}</CardContent>
        </Card>
        {m.simulated.includes('identity') && (
          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>{t('acc.people')}</CardTitle><CardDescription>{t('shell.identityHint')}</CardDescription></CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {identities.map((i) => (
                <button key={i.id} type="button" onClick={() => setIdentity(i.id)} aria-pressed={i.id === identity?.id}
                  className="rounded-[10px] border border-line bg-panel p-3 text-start transition hover:border-line2 aria-pressed:border-accent aria-pressed:bg-wash">
                  <div className="text-13 font-medium text-fg">{i.displayName}</div>
                  <div className="text-12 text-muted">{t(i.roleKey)}</div>
                  <div className="mt-1 text-12 text-dim">{i.tenant ? `${t('shell.tenant')} ${i.tenant}` : t('shell.platformScope')}</div>
                </button>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
