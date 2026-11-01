import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useActivations, useCan, useOperations, usePlugins, useRecords, type ConnectionSpec } from '@/kit/api';
import { ProblemAlert } from '@/kit/governed';
import { StatusPill } from '@/ui/atoms/status-pill';
import { StyleChip } from '@/ui/atoms/style-chip';
import { KpiTile } from '@/ui/molecules/kpi-tile';
import { EmptyState } from '@/ui/molecules/states';
import { ChartCard } from '@/ui/organisms/chart-card';
import { DonutChart } from '@/ui/charts/donut-chart';
import { BarChart } from '@/ui/charts/bar-chart';
import { HeatmapChart } from '@/ui/charts/heatmap-chart';
import { RankedBars } from '@/ui/viz/ranked-bars';
import { PageHeader } from '@/ui/templates/page-header';
import { ChartGrid, KpiGrid, Stack } from '@/ui/templates/section';
import { num, relative, shortDate } from '@/lib/format';
import { usePrefs } from '@/lib/prefs';
import { display, lastDays, recordStatusConfig, STYLE_COLOR, styleOf } from './shared';

const OP_COLOR: Record<string, string> = { succeeded: 'var(--good)', failed: 'var(--bad)', cancelled: 'var(--line-strong)', running: 'var(--info)', stalled: 'var(--warn)', pending: 'var(--fg-dim)' };

export function OverviewPage() {
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const navigate = useNavigate();
  const can = useCan();
  const readable = can('connections:read');
  const records = useRecords<ConnectionSpec>('connections', readable);
  const ops = useOperations();
  const acts = useActivations(readable);
  const plugins = usePlugins();
  const items = useMemo(() => records.data?.items ?? [], [records.data]);
  const now = useMemo(() => new Date(), []);

  const days = useMemo(() => lastDays(30, now), [now]);
  const daily = useMemo(() => days.map((d) => ({ date: d, activations: (acts.data?.items ?? []).filter((a) => a.activatedAt.slice(0, 10) === d).length })), [days, acts.data]);
  const week = (from: number) => daily.slice(daily.length - from - 7, daily.length - from).reduce((s, d) => s + d.activations, 0);
  const thisWeek = week(0); const lastWeek = week(7);

  const byStatus = useMemo(() => (['active', 'draft', 'paused', 'retired'] as const).map((s) => ({ status: s, count: items.filter((r) => r.status === s).length })), [items]);
  const waiting = items.filter((r) => r.current.status === 'submitted');
  const active = items.filter((r) => r.status === 'active').length;

  const opRows = useMemo(() => ops.data?.items ?? [], [ops.data]);
  const recentOps = opRows.filter((o) => now.getTime() - new Date(o.createdAt).getTime() < 7 * 86_400_000);
  const opStatus = (['succeeded', 'failed', 'cancelled', 'running'] as const).map((s) => ({ status: t(`status.${s}`), key: s, count: opRows.filter((o) => o.status === s).length, color: OP_COLOR[s] }));
  const okTrend = days.slice(-14).map((d) => opRows.filter((o) => o.createdAt.slice(0, 10) === d && o.status === 'succeeded').length);

  const heat = useMemo(() => {
    const cells = new Map<string, number>();
    opRows.forEach((o) => { const d = new Date(o.createdAt); const k = `${d.getHours()}:${d.getDay()}`; cells.set(k, (cells.get(k) ?? 0) + 1); });
    const hours = Array.from({ length: 16 }, (_, i) => i + 6);
    return { x: hours.map((h) => `${String(h).padStart(2, '0')}`), y: [0, 1, 2, 3, 4, 5, 6].map((d) => t(`day.${d}`)),
      cells: hours.flatMap((h, xi) => [0, 1, 2, 3, 4, 5, 6].map((d) => [xi, d, cells.get(`${h}:${d}`) ?? 0] as [number, number, number])) };
  }, [opRows, t]);

  const ranked = useMemo(() => {
    const counts = new Map<string, number>();
    items.filter((r) => r.status !== 'retired').forEach((r) => counts.set(`${r.current.spec.connector}@${r.current.spec.connector_version}`, (counts.get(`${r.current.spec.connector}@${r.current.spec.connector_version}`) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([key, value]) => {
      const p = plugins.data?.items.find((x) => `${x.id}@${x.version}` === key);
      return { id: key, name: display(p?.display, lang) || key, subtitle: <StyleChip style={styleOf(p)} className="mt-1 border-0 bg-transparent p-0" />, value, color: STYLE_COLOR[styleOf(p)] };
    });
  }, [items, plugins.data, lang]);

  const statusConfig = recordStatusConfig(t);
  const error = records.error ?? ops.error;

  return (
    <>
      <PageHeader eyebrow={t('overview.eyebrow')} title={t('overview.title')} description={t('overview.desc')} tags={['P13', 'P14', 'P39', 'F11']} />
      <Stack>
        {error && <ProblemAlert error={error} />}
        <KpiGrid>
          <KpiTile loading={records.isLoading} label={t('kpi.active')} value={num(active)} hint={t('kpi.active.hint', { total: items.length })} onOpen={() => navigate('/connections')} tone="good"
            trend={daily.map((_, i) => daily.slice(0, i + 1).reduce((s, d) => s + d.activations, 0))} />
          <KpiTile loading={records.isLoading} label={t('kpi.waiting')} value={num(waiting.length)} hint={t('kpi.waiting.hint')} onOpen={() => navigate('/approvals')} tone="warn" />
          <KpiTile loading={ops.isLoading} label={t('kpi.ops')} value={num(recentOps.filter((o) => o.status === 'succeeded').length)}
            hint={t('kpi.ops.hint', { failed: recentOps.filter((o) => o.status === 'failed').length })} onOpen={() => navigate('/operations')} trend={okTrend} tone="info" />
          <KpiTile loading={acts.isLoading} label={t('kpi.activations')} value={num(thisWeek)} hint={t('kpi.activations.hint')} onOpen={() => navigate('/activations')}
            delta={{ value: thisWeek - lastWeek, format: (v) => num(v) }} trend={daily.slice(-14).map((d) => d.activations)} />
        </KpiGrid>

        <ChartGrid>
          <ChartCard className="lg:col-span-2" title={t('overview.trend.t')} subtitle={t('overview.trend.d')} loading={acts.isLoading}
            table={{ headers: [t('col.date'), t('chart.activations')], rows: daily.map((d) => [shortDate(d.date), d.activations]), numeric: [false, true] }}>
            <BarChart data={daily.map((d) => ({ ...d, label: shortDate(d.date) }))} xKey="label" integer valueFormatter={(v) => num(v)} ariaLabel={t('overview.trend.t')}
              config={{ activations: { label: t('chart.activations'), color: 'var(--accent)' } }} />
          </ChartCard>
          <ChartCard title={t('overview.status.t')} subtitle={t('overview.status.d')} loading={records.isLoading}
            table={{ headers: [t('col.status'), t('col.count')], rows: byStatus.map((s) => [t(`status.${s.status}`), s.count]), numeric: [false, true] }}>
            <DonutChart data={byStatus} nameKey="status" valueKey="count" config={statusConfig} centerLabel={t('chart.connections')} valueFormatter={(v) => num(v)} ariaLabel={t('overview.status.t')} otherLabel={t('chart.other')} />
          </ChartCard>
        </ChartGrid>

        <ChartGrid>
          <ChartCard title={t('overview.connectors.t')} subtitle={t('overview.connectors.d')} loading={records.isLoading || plugins.isLoading}
            table={{ headers: [t('col.connector'), t('col.count')], rows: ranked.map((r) => [r.name, r.value]), numeric: [false, true] }}>
            <RankedBars items={ranked} format={(v) => num(v)} ariaLabel={t('overview.connectors.t')} onSelect={() => navigate('/connections')} />
          </ChartCard>
          <ChartCard title={t('overview.ops.t')} subtitle={t('overview.ops.d')} loading={ops.isLoading}
            table={{ headers: [t('col.status'), t('col.count')], rows: opStatus.map((o) => [o.status, o.count]), numeric: [false, true] }}>
            <BarChart data={opStatus} xKey="status" colorKey="color" layout="horizontal" integer valueFormatter={(v) => num(v)} ariaLabel={t('overview.ops.t')}
              config={{ count: { label: t('col.count'), color: 'var(--accent)' } }} height={200} />
          </ChartCard>
          <ChartCard title={t('overview.queue.t')} subtitle={t('overview.queue.d')} loading={records.isLoading}>
            {waiting.length ? (
              <ul className="flex flex-col divide-y divide-line">
                {waiting.slice(0, 5).map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => navigate(`/connections/${r.id}`)} className="flex w-full items-center gap-3 rounded-[8px] px-1 py-2.5 text-start transition hover:bg-panel2">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-13 font-medium text-fg">{r.current.spec.name}</span>
                        <span className="block truncate text-12 text-dim">v{r.current.version} · {r.current.submittedBy} · {relative(r.updatedAt)}</span>
                      </span>
                      <StatusPill status="submitted" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : <EmptyState title={t('overview.queue.empty')} description={t('appr.empty.d')} className="py-6" />}
          </ChartCard>
        </ChartGrid>

        <ChartCard title={t('overview.heat.t')} subtitle={t('overview.heat.d')} loading={ops.isLoading}
          table={{ headers: [t('col.day'), ...heat.x], rows: heat.y.map((d, yi) => [d, ...heat.x.map((_, xi) => heat.cells.find((c) => c[0] === xi && c[1] === yi)![2])]), numeric: [false, ...heat.x.map(() => true)] }}>
          <HeatmapChart xLabels={heat.x} yLabels={heat.y} cells={heat.cells} valueLabel={t('nav.operations')} ariaLabel={t('overview.heat.t')} />
        </ChartCard>
      </Stack>
    </>
  );
}

