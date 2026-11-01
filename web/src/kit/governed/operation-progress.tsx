import { useTranslation } from 'react-i18next';
import type { Operation } from '@/kit/api';
import { StatusPill } from '@/ui/atoms/status-pill';
import { cn } from '@/lib/utils';

const BAR: Record<string, string> = { running: 'bg-info', pending: 'bg-line2', succeeded: 'bg-good', failed: 'bg-bad', cancelled: 'bg-line2', stalled: 'bg-warn' };

export function OperationProgress({ op, compact }: { op: Operation; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={cn('flex items-center gap-3', compact ? 'min-w-40' : 'w-full')}>
      {!compact && <StatusPill status={op.status} />}
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel2" role="progressbar" aria-valuenow={op.progress} aria-valuemin={0} aria-valuemax={100} aria-label={t('col.progress')}>
        <div className={cn('h-full rounded-full transition-[width] duration-500', BAR[op.status])} style={{ width: `${op.progress}%` }} />
      </div>
      <span className="num w-10 text-end text-12 text-muted">{op.progress}%</span>
    </div>
  );
}
