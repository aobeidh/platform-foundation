import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export type IntegrationStyle = 'api' | 'event' | 'file' | 'hook';
const DOT: Record<IntegrationStyle, string> = { api: 'bg-api', event: 'bg-event', file: 'bg-file', hook: 'bg-hook' };

/** An integration style chip: the colour dot always sits next to the written name (never colour alone). */
export function StyleChip({ style, className }: { style: IntegrationStyle; className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2 py-0.5 text-12 font-medium text-fg', className)}>
      <span aria-hidden className={cn('size-2 rounded-full', DOT[style])} />
      {t(`style.${style}`)}
    </span>
  );
}
