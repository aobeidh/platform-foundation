import type { TFunction } from 'i18next';
import type { ChartConfig } from '@/ui/charts/echart';
import type { IntegrationStyle } from '@/ui/atoms/style-chip';
import type { Connection, PluginInfo, RecordStatus } from '@/kit/api';

/** The integration style a connector serves, read from the capabilities it declares. */
export function styleOf(plugin?: Pick<PluginInfo, 'capabilities'>): IntegrationStyle {
  const caps = new Set(plugin?.capabilities ?? []);
  if (caps.has('file')) return 'file';
  if (caps.has('publish') || caps.has('subscribe')) return 'event';
  if (caps.has('webhook')) return 'hook';
  return 'api';
}

export const STYLE_COLOR: Record<IntegrationStyle, string> = { api: 'var(--s-api)', event: 'var(--s-event)', file: 'var(--s-file)', hook: 'var(--s-hook)' };

export const STATUS_COLOR: Record<RecordStatus, string> = { active: 'var(--good)', draft: 'var(--fg-dim)', paused: 'var(--warn)', retired: 'var(--line-strong)' };

export const recordStatusConfig = (t: TFunction): ChartConfig => ({
  active: { label: t('status.active'), color: STATUS_COLOR.active },
  draft: { label: t('status.draft'), color: 'var(--info)' },
  paused: { label: t('status.paused'), color: STATUS_COLOR.paused },
  retired: { label: t('status.retired'), color: STATUS_COLOR.retired },
});

export const pluginFor = (plugins: PluginInfo[] | undefined, c: Connection) =>
  plugins?.find((p) => p.id === c.current.spec.connector && p.version === c.current.spec.connector_version);

export const display = (d: Record<string, string> | undefined, lang: string) => d?.[lang] ?? d?.en ?? '';

/** Day buckets for the last n days, oldest first, as ISO dates. */
export function lastDays(n: number, now = new Date()) {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getTime() - (n - 1 - i) * 86_400_000);
    return d.toISOString().slice(0, 10);
  });
}
