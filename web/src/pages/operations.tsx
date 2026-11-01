import { useTranslation } from 'react-i18next';
import { useCancelOperation, useOperations, type Operation } from '@/kit/api';
import { OperationProgress, ProblemAlert, problemText } from '@/kit/governed';
import { Button } from '@/ui/atoms/button';
import { Mono } from '@/ui/atoms/misc';
import { StatusPill } from '@/ui/atoms/status-pill';
import { DataTable } from '@/ui/organisms/data-table';
import { PageHeader } from '@/ui/templates/page-header';
import { dateTime, relative } from '@/lib/format';
import { useSetStage } from '@/app/stage';

export function OperationsPage() {
  const { t } = useTranslation();
  const ops = useOperations();
  const cancel = useCancelOperation();
  useSetStage('run');
  const live = ops.data?.items.some((o) => o.status === 'running' || o.status === 'pending');
  return (
    <>
      <PageHeader eyebrow={t('ops.eyebrow')} title={t('ops.title')} description={t('ops.desc')} tags={['P39', 'I12', 'ADR 0004']}
        meta={live ? <span className="inline-flex items-center gap-1.5 text-12 text-info"><span className="size-1.5 animate-pulse rounded-full bg-info" />{t('ops.live')}</span> : undefined} />
      {cancel.error && <div className="mb-4"><ProblemAlert error={cancel.error} /></div>}
      <DataTable<Operation> rows={ops.data?.items} rowKey={(o) => o.id} caption={t('ops.title')} csvName="operations" loading={ops.isLoading}
        error={ops.error ? { cause: problemText(ops.error), onRetry: () => void ops.refetch() } : null}
        empty={{ title: t('ops.empty.t'), description: t('ops.empty.d') }}
        columns={[
          { key: 'id', header: 'ID', value: (o) => o.id, render: (o) => <Mono>{o.id.slice(-8)}</Mono> },
          { key: 'kind', header: t('col.kind'), value: (o) => o.kind, render: (o) => <span className="font-mono text-12">{o.kind}</span> },
          { key: 'status', header: t('col.status'), value: (o) => t(`status.${o.status}`), render: (o) => <StatusPill status={o.status} /> },
          { key: 'progress', header: t('col.progress'), numeric: true, value: (o) => o.progress, render: (o) => <OperationProgress op={o} compact /> },
          { key: 'result', header: t('col.result'), value: (o) => o.error?.detail ?? (o.result ? JSON.stringify(o.result) : ''),
            render: (o) => o.error ? <span className="text-12 text-bad">{o.error.detail}</span> : o.result ? <span className="text-12 text-muted">{t('ops.sent', { n: (o.result as { sent?: number }).sent ?? 0 })}</span> : null },
          { key: 'createdBy', header: t('col.createdBy'), value: (o) => o.createdBy },
          { key: 'started', header: t('col.started'), value: (o) => o.createdAt, render: (o) => <span title={dateTime(o.createdAt)} className="text-muted">{relative(o.createdAt)}</span> },
          { key: 'cancel', header: '', render: (o) => (o.status === 'running' || o.status === 'pending') && !o.cancelRequested
            ? <Button size="xs" variant="outline" loading={cancel.isPending && cancel.variables === o.id} onClick={(e) => { e.stopPropagation(); cancel.mutate(o.id); }}>{t('ops.cancel')}</Button> : null },
        ]} />
    </>
  );
}
