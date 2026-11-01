import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Pencil, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCan, useKinds, useOperation, usePlugins, useRecord, useSend, useSendBatch, useVersions, type ConnectionSpec, type Connection } from '@/kit/api';
import { GovernedActions, LifecycleGates, OperationProgress, ProblemAlert, problemText } from '@/kit/governed';
import { Badge } from '@/ui/atoms/badge';
import { Button } from '@/ui/atoms/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/atoms/card';
import { Input } from '@/ui/atoms/input';
import { Mono } from '@/ui/atoms/misc';
import { StatusPill } from '@/ui/atoms/status-pill';
import { StyleChip } from '@/ui/atoms/style-chip';
import { Textarea } from '@/ui/atoms/textarea';
import { ErrorState, LoadingState } from '@/ui/molecules/states';
import { TabBar } from '@/ui/molecules/tab-bar';
import { DataTable } from '@/ui/organisms/data-table';
import { PageHeader } from '@/ui/templates/page-header';
import { dateTime, relative } from '@/lib/format';
import { usePrefs } from '@/lib/prefs';
import { useSetStage } from '@/app/stage';
import { ConnectionForm } from './connection-form';
import { display, pluginFor, styleOf } from './shared';

const STAGE: Record<string, string> = { draft: 'draft', returned: 'change', tested: 'submit', submitted: 'approve', active: 'run', superseded: 'run', retired: 'retire', discarded: 'retire' };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 border-b border-line py-2 text-13 last:border-0"><dt className="text-muted">{label}</dt><dd className="min-w-0 text-fg">{children}</dd></div>;
}

function SendPanel({ record }: { record: Connection }) {
  const { t } = useTranslation();
  const can = useCan();
  const send = useSend();
  const batch = useSendBatch();
  const [payload, setPayload] = useState('{\n  "text": " hello"\n}');
  const [count, setCount] = useState('25');
  const [opId, setOpId] = useState<string | null>(null);
  const op = useOperation(opId);
  const live = record.status === 'active';
  let parsed: Record<string, unknown> | null = null;
  try { const v = JSON.parse(payload); parsed = v && typeof v === 'object' && !Array.isArray(v) ? v : null; } catch { parsed = null; }
  const allowed = can('connections:use');
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>{t('send.t')}</CardTitle><CardDescription>{t('send.d')}</CardDescription></CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!live && <p className="rounded-[10px] bg-warn/10 px-3 py-2 text-13 text-warn">{t('send.notLive')}</p>}
          <div className="grid gap-1.5">
            <label htmlFor="payload" className="text-13 font-medium">{t('send.payload')}</label>
            <Textarea id="payload" dir="ltr" className="min-h-28 font-mono text-12" value={payload} onChange={(e) => setPayload(e.target.value)} aria-invalid={!parsed} aria-describedby="payload-hint" />
            <p id="payload-hint" className={parsed ? 'text-12 text-dim' : 'text-12 text-bad'}>{parsed ? t('send.payloadHint') : t('send.badJson')}</p>
          </div>
          <div><Button disabled={!parsed || !allowed || !live} loading={send.isPending} onClick={() => parsed && send.mutate({ id: record.id, payload: parsed })}>
            {send.isPending ? t('send.going') : t('send.go')}</Button>
            {!allowed && <span className="ms-3 text-12 text-dim">{t('act.why.cap', { cap: 'connections:use' })}</span>}</div>
          {send.error && <ProblemAlert error={send.error} />}
          {send.data && (
            <div><div className="mb-1 text-12 font-medium text-good">{t('send.result')}</div>
              <pre dir="ltr" className="overflow-x-auto rounded-[10px] border border-line bg-panel2 p-3 font-mono text-12 text-fg">{JSON.stringify(send.data, null, 2)}</pre></div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>{t('send.batch.t')}</CardTitle><CardDescription>{t('send.batch.d')}</CardDescription></CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid max-w-56 gap-1.5">
            <label htmlFor="count" className="text-13 font-medium">{t('send.batch.count')}</label>
            <Input id="count" inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value.replace(/\D/g, ''))} />
          </div>
          <div><Button variant="secondary" disabled={!allowed || !live || !Number(count) || Number(count) > 1000} loading={batch.isPending}
            onClick={() => batch.mutate({ id: record.id, payloads: Array.from({ length: Number(count) }, (_, i) => ({ text: ` #${i + 1}` })) }, { onSuccess: (o) => setOpId(o.id) })}>
            {t('send.batch.go')}</Button></div>
          {batch.error && <ProblemAlert error={batch.error} />}
          {op.data && (
            <div className="flex flex-col gap-2 rounded-[10px] border border-line bg-panel p-3" aria-live="polite">
              <div className="flex items-center justify-between gap-2 text-12 text-muted"><Mono>202 Accepted · /api/v1/operations/{op.data.id.slice(-8)}</Mono><Link to="/operations" className="text-accent hover:underline">{t('nav.operations')}</Link></div>
              <OperationProgress op={op.data} />
              {op.data.error && <p className="text-12 text-bad">{op.data.error.detail}</p>}
              {op.data.status === 'succeeded' && <p className="text-12 text-good">{t('ops.sent', { n: (op.data.result as { sent?: number })?.sent ?? 0 })}</p>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function ConnectionDetailPage() {
  const { id = '' } = useParams();
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const can = useCan();
  const record = useRecord<ConnectionSpec>('connections', id);
  const versions = useVersions<ConnectionSpec>('connections', id);
  const kinds = useKinds();
  const plugins = usePlugins();
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  useSetStage(record.data ? (record.data.status === 'paused' ? 'observe' : STAGE[record.data.current.status]) : undefined);

  if (record.isLoading) return <div className="glass"><LoadingState rows={6} /></div>;
  if (record.error || !record.data) return <div className="glass"><ErrorState cause={problemText(record.error)} onRetry={() => void record.refetch()} /></div>;
  const r = record.data;
  const v = r.current;
  const kind = kinds.data?.items.find((k) => k.kind === 'connection');
  const plugin = pluginFor(plugins.data?.items, r);
  const canEdit = can('connections:write') && r.status !== 'retired' && v.status !== 'submitted';

  const overview = (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>{t('detail.spec')}</CardTitle><CardDescription>{t('detail.current', { v: v.version, status: t(`status.${v.status}`) })}</CardDescription></CardHeader>
        <CardContent>
          <dl>
            <Row label={t('col.name')}>{v.spec.name}</Row>
            <Row label={t('col.connector')}><span className="flex flex-wrap items-center gap-2">{display(plugin?.display, lang) || v.spec.connector}<Mono>{v.spec.connector}@{v.spec.connector_version}</Mono><StyleChip style={styleOf(plugin)} /></span></Row>
            {Object.entries(v.spec.config ?? {}).map(([k, val]) => <Row key={k} label={k}><span dir="ltr" className="font-mono text-12">{JSON.stringify(val)}</span></Row>)}
          </dl>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader><CardTitle>{t('detail.checks')}</CardTitle></CardHeader>
          <CardContent>
            {v.testResult ? (
              <ul className="flex flex-col gap-2">{v.testResult.map((c) => (
                <li key={c.name} className="flex items-start gap-2 text-13">
                  {c.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0 text-bad" aria-hidden />}
                  <span><span className="font-medium">{c.name}</span> <Badge tone={c.ok ? 'good' : 'bad'} className="ms-1">{t(c.ok ? 'status.passed' : 'status.failed')}</Badge><span className="mt-0.5 block text-12 text-muted">{c.detail}</span></span>
                </li>))}</ul>
            ) : <p className="text-13 text-muted">{t('detail.checks.none')}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{t('detail.people')}</CardTitle></CardHeader>
          <CardContent><dl>
            <Row label={t('col.createdBy')}>{v.createdBy}</Row>
            <Row label={t('detail.editedBy')}>{v.editedBy.join(', ')}</Row>
            <Row label={t('col.submittedBy')}>{v.submittedBy ?? '—'}</Row>
            <Row label={t('col.approvedBy')}>{v.approvedBy ?? '—'}</Row>
            <Row label={t('detail.approval')}>{kind ? t(`approval.${kind.approval}`) : '—'}</Row>
          </dl></CardContent>
        </Card>
      </div>
    </div>
  );

  return (
    <>
      <Link to="/connections" className="mb-4 inline-flex items-center gap-1.5 text-13 text-muted hover:text-fg"><ArrowLeft className="size-4 rtl:-scale-x-100" aria-hidden />{t('detail.back')}</Link>
      <PageHeader eyebrow={t('conn.eyebrow')} title={v.spec.name}
        meta={<><StatusPill status={r.status} />{v.status !== r.status && <StatusPill status={v.status} />}<Mono>{r.id.slice(-12)}</Mono><span className="text-12 text-dim">{t('detail.revision', { r: r.revision })} · {relative(r.updatedAt)}</span></>}
        actions={canEdit && <Button variant="secondary" onClick={() => setEditing(true)}><Pencil />{['draft', 'tested'].includes(v.status) ? t('act.edit') : t('act.newDraft')}</Button>} />

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader><CardTitle>{t('detail.gates')}</CardTitle>
            {r.activeVersion && r.activeVersion !== r.currentVersion && <CardDescription>{t('detail.liveNote', { v: r.activeVersion, c: r.currentVersion })}</CardDescription>}</CardHeader>
          <CardContent className="flex flex-col gap-4">
            {v.status === 'returned' && v.reason && <p className="rounded-[10px] bg-warn/10 px-3 py-2 text-13 text-warn">{t('detail.returned', { reason: v.reason })}</p>}
            <LifecycleGates record={r} requireTest={kind?.requireTest ?? true} />
            {kind && <GovernedActions record={r} kind={kind} onDone={(text, ok) => { setNotice(text ? { text, ok } : null); if (!text) void record.refetch(); }} />}
            {notice && <p role="status" className={notice.ok ? 'text-13 text-good' : 'text-13 text-bad'}>{notice.text}</p>}
          </CardContent>
        </Card>
        <TabBar tabs={[
          { id: 'overview', label: t('detail.overview'), content: overview },
          { id: 'versions', label: t('detail.versions'), count: versions.data?.length, content: (
            <DataTable rows={versions.data} rowKey={(x) => String(x.version)} caption={t('detail.versions')} searchable={false} loading={versions.isLoading}
              columns={[
                { key: 'version', header: t('col.version'), numeric: true, value: (x) => x.version },
                { key: 'status', header: t('col.status'), value: (x) => x.status, render: (x) => <StatusPill status={x.status} /> },
                { key: 'createdBy', header: t('col.createdBy'), value: (x) => x.createdBy },
                { key: 'submittedBy', header: t('col.submittedBy'), value: (x) => x.submittedBy ?? '—' },
                { key: 'approvedBy', header: t('col.approvedBy'), value: (x) => x.approvedBy ?? '—' },
                { key: 'config', header: t('conn.form.settings'), render: (x) => <span dir="ltr" className="font-mono text-11 text-muted">{JSON.stringify(x.spec.config)}</span> },
              ]} />) },
          { id: 'send', label: t('detail.send'), content: <SendPanel record={r} /> },
        ]} />
        <p className="text-12 text-dim">{t('col.updated')}: {dateTime(r.updatedAt)}</p>
      </div>
      <ConnectionForm open={editing} onOpenChange={setEditing} record={r} onSaved={() => setNotice({ text: t('conn.form.saved'), ok: true })} />
    </>
  );
}
