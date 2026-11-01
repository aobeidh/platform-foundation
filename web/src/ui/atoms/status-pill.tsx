import { useTranslation } from 'react-i18next';
import { Badge, type Tone } from './badge';

/** One table maps every status the platform knows to a tone. The status is always written out. */
export const STATUS_TONE: Record<string, Tone> = {
  draft: 'neutral', tested: 'info', submitted: 'warn', active: 'good', paused: 'warn', retired: 'neutral',
  superseded: 'neutral', pending: 'neutral', running: 'info', stalled: 'warn', succeeded: 'good', failed: 'bad',
  cancelled: 'neutral', passed: 'good', warning: 'warn', blocked: 'bad', healthy: 'good', degraded: 'warn',
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge tone={STATUS_TONE[status] ?? 'neutral'} dot className={className}>
      {t(`status.${status}`, { defaultValue: status })}
    </Badge>
  );
}
