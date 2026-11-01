import { AlertTriangle, Inbox, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/ui/atoms/button';
import { Skeleton } from '@/ui/atoms/skeleton';
import { cn } from '@/lib/utils';

export function EmptyState({ title, description, action, icon, className }: {
  title: string; description: string; action?: React.ReactNode; icon?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center gap-2 px-6 py-10 text-center', className)}>
      <span className="mb-1 grid size-11 place-items-center rounded-[12px] bg-panel2 text-muted [&_svg]:size-5">{icon ?? <Inbox />}</span>
      <p className="text-15 font-semibold text-fg">{title}</p>
      <p className="max-w-sm text-13 text-muted">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ title, cause, correlationId, onRetry, className }: {
  title?: string; cause: string; correlationId?: string; onRetry?: () => void; className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div role="alert" className={cn('flex flex-col items-center gap-2 px-6 py-10 text-center', className)}>
      <span className="mb-1 grid size-11 place-items-center rounded-[12px] bg-bad/10 text-bad"><AlertTriangle className="size-5" aria-hidden /></span>
      <p className="text-15 font-semibold text-fg">{title ?? t('states.error.t')}</p>
      <p className="max-w-md text-13 text-muted">{cause}</p>
      {correlationId && <p className="font-mono text-11 text-dim">{t('common.correlation', { id: correlationId })}</p>}
      {onRetry && <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>{t('common.retry')}</Button>}
    </div>
  );
}

export function ForbiddenState({ capability }: { capability: string }) {
  const { t } = useTranslation();
  return <EmptyState icon={<Lock />} title={t('states.forbidden.t')} description={t('states.forbidden.d', { cap: capability })} />;
}

export function LoadingState({ rows = 5, className }: { rows?: number; className?: string }) {
  const { t } = useTranslation();
  return (
    <div className={cn('flex flex-col gap-2 p-4', className)} aria-busy aria-label={t('states.loading.t')}>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-9" style={{ width: `${100 - (i % 3) * 8}%` }} />)}
    </div>
  );
}
