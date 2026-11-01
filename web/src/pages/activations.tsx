import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useActivations, useCan, useRecords, type Activation, type ConnectionSpec } from '@/kit/api';
import { problemText } from '@/kit/governed';
import { Mono } from '@/ui/atoms/misc';
import { ForbiddenState } from '@/ui/molecules/states';
import { DataTable } from '@/ui/organisms/data-table';
import { PageHeader } from '@/ui/templates/page-header';
import { dateTime } from '@/lib/format';
import { useSetStage } from '@/app/stage';

export function ActivationsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const can = useCan();
  const readable = can('connections:read');
  const acts = useActivations(readable);
  const records = useRecords<ConnectionSpec>('connections', readable);
  useSetStage('observe');
  const name = (id: string) => records.data?.items.find((r) => r.id === id)?.current.spec.name ?? id.slice(-8);
  const rows = [...(acts.data?.items ?? [])].reverse();
  return (
    <>
      <PageHeader eyebrow={t('actv.eyebrow')} title={t('actv.title')} description={t('actv.desc')} tags={['P18', 'P19', 'I6']} />
      {!readable ? <div className="glass"><ForbiddenState capability="connections:read" /></div> : (
        <DataTable<Activation> rows={rows} rowKey={(a) => a.eventId} caption={t('actv.title')} csvName="activations" loading={acts.isLoading}
          error={acts.error ? { cause: problemText(acts.error), onRetry: () => void acts.refetch() } : null}
          empty={{ title: t('actv.empty.t'), description: t('actv.empty.d') }} onRowClick={(a) => navigate(`/connections/${a.connectionId}`)}
          columns={[
            { key: 'connection', header: t('col.connection'), value: (a) => name(a.connectionId), render: (a) => <span className="font-medium">{name(a.connectionId)}</span> },
            { key: 'version', header: t('col.version'), numeric: true, value: (a) => a.version },
            { key: 'tenant', header: t('col.tenant'), value: (a) => a.tenant ?? '—' },
            { key: 'activatedAt', header: t('col.activatedAt'), value: (a) => a.activatedAt, render: (a) => dateTime(a.activatedAt) },
            { key: 'event', header: t('col.event'), value: (a) => a.eventId, render: (a) => <Mono>{a.eventId.slice(-12)}</Mono> },
          ]} />
      )}
    </>
  );
}
