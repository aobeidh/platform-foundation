import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import type { TFunction } from 'i18next';
import { Check, Copy, Moon, Plus, Save, Sun, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/ui/atoms/badge';
import { Button } from '@/ui/atoms/button';
import { Checkbox } from '@/ui/atoms/checkbox';
import { Form } from '@/ui/atoms/form';
import { Input } from '@/ui/atoms/input';
import { Delta, Kbd, Mono } from '@/ui/atoms/misc';
import { Segmented } from '@/ui/atoms/segmented';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/ui/atoms/select';
import { Slider } from '@/ui/atoms/slider';
import { StatusPill } from '@/ui/atoms/status-pill';
import { StyleChip } from '@/ui/atoms/style-chip';
import { Switch } from '@/ui/atoms/switch';
import { Textarea } from '@/ui/atoms/textarea';
import { FieldRow, InlineField } from '@/ui/molecules/form-field';
import { KpiTile } from '@/ui/molecules/kpi-tile';
import { ColorSwatch, TypeSample } from '@/ui/molecules/samples';
import { EmptyState, ErrorState, LoadingState } from '@/ui/molecules/states';
import { TabBar } from '@/ui/molecules/tab-bar';
import { ChartCard } from '@/ui/organisms/chart-card';
import { DataTable } from '@/ui/organisms/data-table';
import { AreaChart } from '@/ui/charts/area-chart';
import { BarChart } from '@/ui/charts/bar-chart';
import { DonutChart } from '@/ui/charts/donut-chart';
import { FanChart } from '@/ui/charts/fan-chart';
import { HeatmapChart } from '@/ui/charts/heatmap-chart';
import { Sparkline } from '@/ui/charts/sparkline';
import { LineageGraph } from '@/ui/viz/lineage-graph';
import { PipelineGates } from '@/ui/viz/pipeline-gates';
import { RankedBars } from '@/ui/viz/ranked-bars';
import { PageHeader } from '@/ui/templates/page-header';
import { Section, Stack } from '@/ui/templates/section';
import { compact, num, pct, shortDate } from '@/lib/format';
import { usePrefs } from '@/lib/prefs';
import { labDaily, labForecast, labLineage, labRows, labTraffic } from '@/data/lab';
import { STYLE_COLOR } from '../shared';

export const labSections = (t: TFunction) => [
  'colors', 'type', 'buttons', 'badges', 'kpi', 'table', 'form', 'tabs', 'states', 'charts', 'viz',
].map((id) => ({ id, title: t(`sec.${id}.t`) }));

function Install({ name }: { name: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const cmd = `npx shadcn add @platform/${name}`;
  return (
    <button type="button" onClick={() => { void navigator.clipboard?.writeText(cmd).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="inline-flex items-center gap-1.5 rounded-[8px] border border-line bg-panel2 px-2 py-1 font-mono text-11 text-muted transition hover:text-fg" aria-label={`${t('common.copy')}: ${cmd}`}>
      {copied ? <Check className="size-3 text-good" /> : <Copy className="size-3" />}{cmd}
    </button>
  );
}

function LabForm() {
  const { t } = useTranslation();
  const schema = z.object({
    name: z.string().min(3, `form.err.min|${JSON.stringify({ n: 3 })}`),
    connector: z.string().min(1, 'form.err.choose'),
    timeout: z.coerce.number({ invalid_type_error: 'form.err.number' }).min(100, `form.err.range|${JSON.stringify({ min: 100, max: 30000 })}`).max(30000, `form.err.range|${JSON.stringify({ min: 100, max: 30000 })}`),
    code: z.string().regex(/^[A-Za-z0-9-]+$/, 'form.err.pattern'),
    notes: z.string().max(200, `form.err.max|${JSON.stringify({ n: 200 })}`),
  });
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), mode: 'onChange',
    defaultValues: { name: 'Customs declarations', connector: 'rest-api', timeout: 8000, code: 'ZATCA 01', notes: '' } });
  const [retry, setRetry] = useState(true);
  const [notify, setNotify] = useState(false);
  const [batch, setBatch] = useState([250]);
  const [env, setEnv] = useState<'dev' | 'test' | 'prod'>('test');
  const [status, setStatus] = useState<'idle' | 'error' | 'saved'>('idle');
  useEffect(() => { void form.trigger('code'); }, [form]);
  return (
    <Form {...form}>
      <form noValidate onSubmit={form.handleSubmit(() => setStatus('saved'), () => setStatus('error'))} className="grid gap-5 md:grid-cols-2">
        <FieldRow control={form.control} name="name" label={t('lab.form.text')} hint={t('lab.form.textHint')}>{(f) => <Input {...f} />}</FieldRow>
        <FieldRow control={form.control} name="connector" label={t('lab.form.select')}>
          {(f) => (
            <Select value={f.value} onValueChange={f.onChange}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{labTraffic.map((x) => <SelectItem key={x.id} value={x.id}>{x.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </FieldRow>
        <FieldRow control={form.control} name="timeout" label={t('lab.form.timeout')} hint={t('lab.form.timeoutHint')}>{(f) => <Input {...f} inputMode="numeric" unit="ms" />}</FieldRow>
        <FieldRow control={form.control} name="code" label={t('lab.form.code')}>{(f) => <Input {...f} className="font-mono" />}</FieldRow>
        <FieldRow control={form.control} name="notes" label={t('lab.form.notes')} className="md:col-span-2">{(f) => <Textarea {...f} />}</FieldRow>
        <InlineField id="retry" label={t('lab.form.switch')} hint={t('lab.form.switchHint')} control={<Switch id="retry" checked={retry} onCheckedChange={setRetry} aria-describedby="retry-hint" />} />
        <div className="flex items-center gap-2 rounded-[10px] border border-line bg-panel px-3 py-2.5">
          <Checkbox id="notify" checked={notify} onCheckedChange={(v) => setNotify(v === true)} />
          <label htmlFor="notify" className="text-13 font-medium">{t('lab.form.check')}</label>
        </div>
        <div className="grid gap-2">
          <div className="flex items-center justify-between"><label id="batch-l" className="text-13 font-medium">{t('lab.form.slider')}</label><span className="num text-13 text-fg">{num(batch[0])}</span></div>
          <Slider aria-labelledby="batch-l" value={batch} onValueChange={setBatch} min={10} max={1000} step={10} />
        </div>
        <div className="grid gap-2">
          <span className="text-13 font-medium">{t('lab.form.segmented')}</span>
          <Segmented ariaLabel={t('lab.form.segmented')} value={env} onValueChange={setEnv}
            options={[{ value: 'dev', label: t('env.dev') }, { value: 'test', label: t('env.test') }, { value: 'prod', label: t('env.prod') }]} />
        </div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Button type="submit"><Save />{t('lab.form.submit')}</Button>
          <span role="status">
            {status === 'error' && <span className="text-13 text-bad">{t('lab.form.fix')}</span>}
            {status === 'saved' && <Badge tone="good" dot>{t('lab.form.saved')}</Badge>}
          </span>
        </div>
      </form>
    </Form>
  );
}

export function DesignLabPage() {
  const { t } = useTranslation();
  const { theme, setTheme } = usePrefs();
  const colors = [
    ['accent', '--accent', 'text-accent'], ['good', '--good', 'text-good'], ['warn', '--warn', 'text-warn'], ['bad', '--bad', 'text-bad'],
    ['info', '--info', 'text-info'], ['forecast', '--forecast', 'text-forecast'], ['api', '--s-api', 'bg-api'], ['event', '--s-event', 'bg-event'],
    ['file', '--s-file', 'bg-file'], ['hook', '--s-hook', 'bg-hook'],
  ] as const;
  const trafficTotal = labTraffic.reduce((s, x) => s + x.value, 0);
  const hours = Array.from({ length: 16 }, (_, i) => String(i + 6).padStart(2, '0'));
  const heat = hours.flatMap((_, x) => [0, 1, 2, 3, 4, 5, 6].map((y) => [x, y, Math.max(0, Math.round((y === 5 || y === 6 ? 2 : 9) * Math.sin(((x + 2) / 17) * Math.PI) + ((x * 7 + y * 3) % 4)))] as [number, number, number]));
  const dailyConfig = { api: { label: t('style.api'), color: 'var(--s-api)' }, event: { label: t('style.event'), color: 'var(--s-event)' }, file: { label: t('style.file'), color: 'var(--s-file)' } };

  return (
    <>
      <PageHeader eyebrow={t('lab.eyebrow')} title={t('lab.title')} description={t('lab.desc')} tags={['F20', 'web-kit 0.3']}
        actions={<Segmented ariaLabel={t('shell.theme')} value={theme} onValueChange={setTheme}
          options={[{ value: 'light', label: t('lab.light'), icon: <Sun /> }, { value: 'dark', label: t('lab.dark'), icon: <Moon /> }]} />} />
      <Stack>
        <Section id="colors" title={t('sec.colors.t')} description={t('sec.colors.d')}>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {colors.map(([k, v, u]) => <ColorSwatch key={k} name={k} cssVar={v} meaning={t(`color.${k}`)} utility={u} />)}
          </div>
          <h3 className="mb-3 mt-6 text-15 font-semibold">{t('sec.surfaces.t')}</h3>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <ColorSwatch name={t('surf.canvas')} cssVar="--bg-0" meaning="bg-bg" utility="--bg-0" />
            <ColorSwatch name={t('surf.card')} cssVar="--card" meaning="bg-card · glass" utility="--card" />
            <ColorSwatch name={t('surf.fill')} cssVar="--panel-strong" meaning="bg-panel2" utility="--panel-strong" />
            <ColorSwatch name={t('surf.line')} cssVar="--line" meaning="border-line" utility="--line" />
          </div>
          <div className="mt-4 flex flex-wrap gap-6 text-[13.5px]">
            <span className="text-fg">{t('text.primary')}</span><span className="text-muted">{t('text.secondary')}</span><span className="text-dim">{t('text.tertiary')}</span>
          </div>
        </Section>

        <Section id="type" title={t('sec.type.t')} description={t('sec.type.d')}>
          <TypeSample label={t('type.page')} spec="26/30 px · 600 · tight" className="text-26 font-semibold tracking-tight md:text-30" sample={t('overview.title')} />
          <TypeSample label={t('type.section')} spec="20 px · 600" className="text-20 font-semibold tracking-tight" sample={t('overview.trend.t')} />
          <TypeSample label={t('type.card')} spec="15 px · 600" className="text-15 font-semibold" sample={t('send.t')} />
          <TypeSample label={t('type.body')} spec="13.5 px · 400" className="text-[13.5px]" sample={t('conn.form.desc')} />
          <TypeSample label={t('type.caption')} spec="12 px · dim" className="text-12 text-dim" sample={t('lab.form.timeoutHint')} />
          <TypeSample label={t('type.eyebrow')} spec="12 px · 600 · caps · 0.08em" className="eyebrow" sample={t('grp.integrations')} />
          <TypeSample label={t('type.kpi')} spec="28 px · 600 · tabular" className="num text-28 font-semibold" sample={num(428_612)} />
        </Section>

        <Section id="buttons" title={t('sec.buttons.t')} description={t('sec.buttons.d')} action={<Install name="button" />}>
          <div className="flex flex-wrap items-center gap-2">
            <Button><Plus />{t('btn.primary')}</Button><Button variant="secondary">{t('btn.secondary')}</Button><Button variant="outline">{t('btn.outline')}</Button>
            <Button variant="ghost">{t('btn.ghost')}</Button><Button variant="accent">{t('btn.accent')}</Button><Button variant="destructive"><Trash2 />{t('btn.danger')}</Button>
            <Button loading>{t('btn.loading')}</Button><Button disabled>{t('btn.disabled')}</Button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2"><span className="text-12 text-dim">{t('btn.sizes')}</span>
            {(['xs', 'sm', 'default', 'lg'] as const).map((s) => <Button key={s} size={s} variant="secondary">{s}</Button>)}
            <Button size="icon" variant="secondary" aria-label={t('common.copy')}><Copy /></Button><Kbd>Ctrl K</Kbd>
          </div>
        </Section>

        <Section id="badges" title={t('sec.badges.t')} description={t('sec.badges.d')} action={<Install name="status-pill" />}>
          <div className="flex flex-wrap gap-2">{(['neutral', 'selected', 'good', 'warn', 'bad', 'info', 'forecast', 'money'] as const).map((tone) => <Badge key={tone} tone={tone}>{tone}</Badge>)}</div>
          <div className="mt-3 flex flex-wrap gap-2">{['draft', 'tested', 'submitted', 'active', 'paused', 'retired', 'running', 'stalled', 'succeeded', 'failed', 'cancelled'].map((s) => <StatusPill key={s} status={s} />)}</div>
          <div className="mt-3 flex flex-wrap items-center gap-2"><span className="text-12 text-dim">{t('lab.styles')}</span>{(['api', 'event', 'file', 'hook'] as const).map((s) => <StyleChip key={s} style={s} />)}
            <Delta value={12} format={(v) => num(v)} /><Delta value={-4} format={(v) => pct(v / 100)} /><Delta value={3} goodWhen="down" format={(v) => num(v)} /></div>
        </Section>

        <Section id="kpi" title={t('sec.kpi.t')} description={t('sec.kpi.d')} bare action={<Install name="kpi-tile" />}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile label={t('kpi.active')} value={num(9)} hint={t('kpi.active.hint', { total: 13 })} delta={{ value: 2, format: (v) => num(v) }} trend={[3, 4, 4, 5, 6, 6, 7, 8, 9]} tone="good" onOpen={() => {}} />
            <KpiTile label={t('kpi.waiting')} value={num(3)} hint={t('kpi.waiting.hint')} delta={{ value: 1, format: (v) => num(v), goodWhen: 'down' }} trend={[1, 2, 1, 3, 2, 2, 3]} tone="warn" onOpen={() => {}} />
            <KpiTile label={t('chart.sends')} value={compact(428_604)} hint={t('kpi.activations.hint')} delta={{ value: 0.062, format: (v) => pct(v) }} trend={labDaily.map((d) => d.api + d.event + d.file)} onOpen={() => {}} />
            <KpiTile label={t('kpi.ops')} value="—" hint={t('common.loading')} loading />
          </div>
        </Section>

        <Section id="table" title={t('sec.table.t')} description={t('sec.table.d')} bare action={<Install name="data-table" />}>
          <DataTable rows={labRows} rowKey={(r) => r.id} caption={t('sec.table.t')} csvName="design-lab"
            columns={[
              { key: 'name', header: t('col.name'), value: (r) => r.name, render: (r) => <span className="font-medium">{r.name}</span> },
              { key: 'connector', header: t('col.connector'), value: (r) => r.connector, render: (r) => <Mono>{r.connector}</Mono> },
              { key: 'style', header: t('col.style'), value: (r) => r.style, render: (r) => <StyleChip style={r.style} /> },
              { key: 'status', header: t('col.status'), value: (r) => r.status, render: (r) => <StatusPill status={r.status} /> },
              { key: 'version', header: t('col.version'), numeric: true, value: (r) => r.version },
              { key: 'sent', header: t('chart.sends'), numeric: true, value: (r) => r.sent, render: (r) => num(r.sent) },
            ]} />
        </Section>

        <Section id="form" title={t('sec.form.t')} description={t('sec.form.d')} action={<Install name="form-field" />}><LabForm /></Section>

        <Section id="tabs" title={t('sec.tabs.t')} action={<Install name="tab-bar" />}>
          <TabBar param="labtab" tabs={[
            { id: 'summary', label: t('tabs.summary'), content: <p className="text-13 text-muted">{t('tabs.summaryBody')}</p> },
            { id: 'history', label: t('tabs.history'), count: 4, content: <p className="text-13 text-muted">{t('tabs.historyBody')}</p> },
            { id: 'settings', label: t('tabs.settings'), content: <p className="text-13 text-muted">{t('tabs.settingsBody')}</p> },
          ]} />
        </Section>

        <Section id="states" title={t('sec.states.t')} description={t('sec.states.d')} bare action={<Install name="states" />}>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="glass"><EmptyState title={t('conn.empty.t')} description={t('conn.empty.d')} action={<Button size="sm"><Plus />{t('conn.new')}</Button>} /></div>
            <div className="glass"><LoadingState rows={4} /></div>
            <div className="glass"><ErrorState cause={t('lab.error.cause')} correlationId="01a198f2-7c41" onRetry={() => {}} /></div>
          </div>
        </Section>

        <Section id="charts" title={t('sec.charts.t')} description={t('sec.charts.d')} bare>
          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard className="lg:col-span-2" title={t('chart.sends')} subtitle="@platform/area-chart · stacked areas"
              table={{ headers: [t('col.date'), t('style.api'), t('style.event'), t('style.file')], rows: labDaily.map((d) => [shortDate(d.date), d.api, d.event, d.file]), numeric: [false, true, true, true] }}>
              <AreaChart data={labDaily} xKey="date" stacked config={dailyConfig} xFormatter={(d) => shortDate(d)} valueFormatter={(v) => compact(v)} ariaLabel={t('chart.sends')} />
            </ChartCard>
            <ChartCard title={t('lab.ranked.t')} subtitle="@platform/donut-chart"
              table={{ headers: [t('col.connector'), t('chart.sends')], rows: labTraffic.map((x) => [x.name, x.value]), numeric: [false, true] }}>
              <DonutChart data={labTraffic} nameKey="id" valueKey="value" centerLabel={t('chart.total')} valueFormatter={(v) => compact(v)} ariaLabel={t('lab.ranked.t')} otherLabel={t('chart.other')}
                config={Object.fromEntries(labTraffic.map((x) => [x.id, { label: x.name, color: STYLE_COLOR[x.style] }]))} />
            </ChartCard>
            <ChartCard title={t('lab.ranked.t')} subtitle="@platform/bar-chart · horizontal"
              table={{ headers: [t('col.connector'), t('chart.sends')], rows: labTraffic.map((x) => [x.name, x.value]), numeric: [false, true] }}>
              <BarChart data={labTraffic} xKey="name" layout="horizontal" config={{ value: { label: t('chart.sends'), color: 'var(--accent)' } }} valueFormatter={(v) => compact(v)} ariaLabel={t('lab.ranked.t')} height={210} />
            </ChartCard>
            <ChartCard className="lg:col-span-2" title={t('lab.fan.t')} subtitle="@platform/fan-chart · 80% band"
              table={{ headers: ['', t('chart.actual'), t('chart.forecast')], rows: labForecast.map((r) => [r.x, r.actual ?? '', r.forecast ?? '']), numeric: [false, true, true] }}>
              <FanChart data={labForecast} budget={500_000} budgetLabel={t('lab.capacity')} valueFormatter={(v) => compact(v)} ariaLabel={t('lab.fan.t')}
                config={{ actual: { label: t('chart.actual'), color: 'var(--accent)' }, forecast: { label: t('chart.forecast'), color: 'var(--forecast)' } }} />
            </ChartCard>
            <ChartCard className="lg:col-span-2" title={t('overview.heat.t')} subtitle="@platform/heatmap-chart">
              <HeatmapChart xLabels={hours} yLabels={[0, 1, 2, 3, 4, 5, 6].map((d) => t(`day.${d}`))} cells={heat} valueLabel={t('nav.operations')} ariaLabel={t('overview.heat.t')} />
            </ChartCard>
            <ChartCard title={t('chart.sends')} subtitle="@platform/sparkline">
              <div className="flex flex-col gap-4 pt-2">
                {(['accent', 'good', 'bad'] as const).map((tone, i) => <Sparkline key={tone} tone={tone} ariaLabel={tone} height={36} data={labDaily.map((d, j) => d.api / 100 + Math.sin(j / (2 + i)) * 12 * (i + 1))} />)}
              </div>
            </ChartCard>
          </div>
        </Section>

        <Section id="viz" title={t('sec.viz.t')} description={t('sec.viz.d')} bare>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title={t('lab.ranked.t')} subtitle={`@platform/ranked-bars · ${t('lab.ranked.d')}`}>
              <RankedBars items={labTraffic.map((x) => ({ id: x.id, name: x.name, subtitle: <StyleChip style={x.style} className="mt-1 border-0 bg-transparent p-0" />, value: x.value, color: STYLE_COLOR[x.style] }))}
                format={(v) => compact(v)} onSelect={() => {}} ariaLabel={t('lab.ranked.t')} />
              <p className="mt-2 text-12 text-dim">{t('chart.total')}: <span className="num text-fg">{num(trafficTotal)}</span></p>
            </ChartCard>
            <ChartCard title={t('lab.gates.t')} subtitle="@platform/pipeline-gates">
              <PipelineGates ariaLabel={t('lab.gates.t')} pendingLabel={t('gate.pending')} gates={[
                { id: 'd', label: t('gate.draft'), state: 'passed', meta: 'ada' }, { id: 't', label: t('gate.tested'), state: 'passed', meta: '2 ✓' },
                { id: 's', label: t('gate.submitted'), state: 'passed', meta: 'ada' },
                { id: 'a', label: t('gate.approved'), state: 'blocked', reason: t('gate.why.approve', { who: 'ada' }) }, { id: 'l', label: t('gate.live'), state: 'pending' },
              ]} />
            </ChartCard>
          </div>
          <ChartCard className="mt-4" title={t('lab.lineage.t')} subtitle={`@platform/lineage-graph · ${t('lab.lineage.d')}`}>
            <LineageGraph ariaLabel={t('lab.lineage.t')} edges={labLineage.edges} nodes={labLineage.nodes.map((n) => ({ ...n, type: t(n.typeKey) }))} />
          </ChartCard>
        </Section>
      </Stack>
    </>
  );
}
