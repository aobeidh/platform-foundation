import { useTranslation } from 'react-i18next';
import type { GovernedRecord } from '@/kit/api';
import { PipelineGates, type Gate } from '@/ui/viz/pipeline-gates';
import { dateTime } from '@/lib/format';

/** The current version's place in the governed lifecycle, as gates: draft, tested, submitted, approved, running. */
export function LifecycleGates({ record }: { record: GovernedRecord<object> }) {
  const { t } = useTranslation();
  const v = record.current;
  const failed = v.testResult?.filter((c) => !c.ok).length ?? 0;
  const order = ['draft', 'tested', 'submitted', 'active'] as const;
  const reached = v.status === 'superseded' || v.status === 'retired' ? 3 : order.indexOf(v.status as (typeof order)[number]);
  const passed = (i: number) => i <= reached;
  const authors = [...new Set([v.createdBy, ...v.editedBy, ...(v.submittedBy ? [v.submittedBy] : [])])].join(', ');
  const gates: Gate[] = [
    { id: 'draft', label: t('gate.draft'), state: 'passed', meta: v.createdBy },
    { id: 'tested', label: t('gate.tested'), state: passed(1) ? 'passed' : 'blocked',
      reason: failed ? t('gate.why.test', { n: failed }) : t('gate.why.untested'), meta: v.testResult ? `${v.testResult.length} ✓` : undefined },
    { id: 'submitted', label: t('gate.submitted'), state: passed(2) ? 'passed' : 'blocked', reason: t('gate.why.submit'), meta: v.submittedBy ?? undefined },
    { id: 'approved', label: t('gate.approved'), state: passed(3) ? 'passed' : 'blocked', reason: t('gate.why.approve', { who: authors }), meta: v.approvedBy ?? undefined },
    { id: 'live', label: t('gate.live'),
      state: record.status === 'active' && v.status === 'active' ? 'passed' : passed(3) ? 'blocked' : 'pending',
      reason: record.status === 'retired' ? t('gate.why.retired') : t('gate.why.paused'), meta: dateTime(record.updatedAt) },
  ];
  return <PipelineGates gates={gates} ariaLabel={t('detail.gates')} pendingLabel={t('gate.pending')} />;
}
