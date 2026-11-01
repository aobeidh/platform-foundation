import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCan, usePlugins, useRecords, type Connection, type ConnectionSpec } from '@/kit/api';
import { problemText } from '@/kit/governed';
import { Button } from '@/ui/atoms/button';
import { StatusPill } from '@/ui/atoms/status-pill';
import { StyleChip } from '@/ui/atoms/style-chip';
import { ForbiddenState } from '@/ui/molecules/states';
import { DataTable, type Column } from '@/ui/organisms/data-table';
import { PageHeader } from '@/ui/templates/page-header';
import { relative } from '@/lib/format';
import { usePrefs } from '@/lib/prefs';
import { useSetStage } from '@/app/stage';
import { ConnectionForm } from './connection-form';
import { display, pluginFor, styleOf } from './shared';

export function ConnectionsPage() {
  const { t } = useTranslation();
  const { lang } = usePrefs();
  const navigate = useNavigate();
  const can = useCan();
  const readable = can('connections:read');
  const records = useRecords<ConnectionSpec>('connections', readable);
  const plugins = usePlugins();
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState(() => { try { return sessionStorage.getItem('pf-conn-q') ?? ''; } catch { return ''; } });
  useSetStage('draft');

  const columns: Column<Connection>[] = [
    { key: 'name', header: t('col.name'), value: (r) => r.current.spec.name,
      render: (r) => <span className="font-medium text-fg">{r.current.spec.name}</span> },
    { key: 'connector', header: t('col.connector'), value: (r) => `${r.current.spec.connector}@${r.current.spec.connector_version}`,
      render: (r) => { const p = pluginFor(plugins.data?.items, r); return (
        <span className="flex flex-col"><span>{display(p?.display, lang) || r.current.spec.connector}</span><span className="font-mono text-11 text-dim">{r.current.spec.connector}@{r.current.spec.connector_version}</span></span>); } },
    { key: 'style', header: t('col.style'), value: (r) => t(`style.${styleOf(pluginFor(plugins.data?.items, r))}`), render: (r) => <StyleChip style={styleOf(pluginFor(plugins.data?.items, r))} /> },
    { key: 'status', header: t('col.status'), value: (r) => t(`status.${r.status}`), render: (r) => (
      <span className="flex flex-wrap items-center gap-1.5"><StatusPill status={r.status} />
        {r.current.status !== 'active' && r.current.status !== r.status && r.status !== 'retired' && <StatusPill status={r.current.status} />}</span>) },
    { key: 'version', header: t('col.version'), numeric: true, value: (r) => r.currentVersion },
    { key: 'active', header: t('col.active'), numeric: true, value: (r) => r.activeVersion ?? 0, render: (r) => r.activeVersion ?? <span className="text-dim">{t('conn.noActive')}</span> },
    { key: 'updated', header: t('col.updated'), value: (r) => r.updatedAt, render: (r) => <span className="text-muted">{relative(r.updatedAt)}</span> },
  ];

  return (
    <>
      <PageHeader eyebrow={t('conn.eyebrow')} title={t('conn.title')} description={t('conn.desc')} tags={['P13', 'P14', 'F11', 'F12']}
        actions={can('connections:write') && <Button onClick={() => setCreating(true)}><Plus />{t('conn.new')}</Button>} />
      {!readable && !records.isLoading ? <div className="glass"><ForbiddenState capability="connections:read" /></div> : (
        <DataTable rows={records.data?.items} columns={columns} rowKey={(r) => r.id} caption={t('conn.title')} csvName="connections"
          query={query} onQueryChange={(q) => { setQuery(q); try { sessionStorage.setItem('pf-conn-q', q); } catch { /* unavailable */ } }}
          loading={records.isLoading} error={records.error ? { cause: problemText(records.error), onRetry: () => void records.refetch() } : null}
          empty={{ title: t('conn.empty.t'), description: can('connections:write') ? t('conn.empty.d') : t('conn.empty.readonly'),
            action: can('connections:write') ? <Button onClick={() => setCreating(true)}><Plus />{t('conn.new')}</Button> : undefined }}
          onRowClick={(r) => navigate(`/connections/${r.id}`)} />
      )}
      <ConnectionForm open={creating} onOpenChange={setCreating} onSaved={(c) => navigate(`/connections/${c.id}`)} />
    </>
  );
}
