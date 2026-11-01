import { useNavigate } from 'react-router-dom';
import { CheckCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCan, useKinds, useMe, useRecords, type Connection, type ConnectionSpec } from '@/kit/api';
import { GovernedActions } from '@/kit/governed';
import { Badge } from '@/ui/atoms/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/atoms/card';
import { EmptyState, ForbiddenState, LoadingState } from '@/ui/molecules/states';
import { PageHeader } from '@/ui/templates/page-header';
import { Section, Stack } from '@/ui/templates/section';
import { relative } from '@/lib/format';
import { useSetStage } from '@/app/stage';
import { useState } from 'react';

function Item({ r }: { r: Connection }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const kinds = useKinds();
  const kind = kinds.data?.items.find((k) => k.kind === 'connection');
  const [notice, setNotice] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle><button type="button" className="text-start hover:text-accent" onClick={() => navigate(`/connections/${r.id}`)}>{r.current.spec.name}</button></CardTitle>
        <CardDescription>v{r.current.version} · {r.current.spec.connector}@{r.current.spec.connector_version} · {t('col.submittedBy')} {r.current.submittedBy} · {relative(r.updatedAt)}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {r.activeVersion && <p className="text-12 text-dim">{t('detail.liveNote', { v: r.activeVersion, c: r.currentVersion })}</p>}
        {kind && <GovernedActions record={r} kind={kind} onDone={(text) => setNotice(text)} />}
        {notice && <p role="status" className="text-13 text-good">{notice}</p>}
      </CardContent>
    </Card>
  );
}

export function ApprovalsPage() {
  const { t } = useTranslation();
  const can = useCan();
  const me = useMe();
  const records = useRecords<ConnectionSpec>('connections', can('connections:read'));
  useSetStage('approve');
  const waiting = (records.data?.items ?? []).filter((r) => r.current.status === 'submitted');
  const authored = (r: Connection) => r.current.makerChecker && [r.current.createdBy, ...r.current.editedBy, r.current.submittedBy].includes(me.data?.subject ?? '');
  const mine = can('connections:approve') ? waiting.filter((r) => !authored(r)) : [];
  const others = waiting.filter((r) => !mine.includes(r));
  return (
    <>
      <PageHeader eyebrow={t('appr.eyebrow')} title={t('appr.title')} description={t('appr.desc')} tags={['P14', 'P21']} />
      {!can('connections:read') && !me.isLoading ? <div className="glass"><ForbiddenState capability="connections:read" /></div>
        : records.isLoading ? <div className="glass"><LoadingState /></div>
        : !waiting.length ? <div className="glass"><EmptyState icon={<CheckCheck />} title={t('appr.empty.t')} description={t('appr.empty.d')} /></div>
        : (
          <Stack>
            {!can('connections:approve') && <p className="rounded-[10px] bg-info/10 px-3 py-2 text-13 text-info">{t('appr.noCap')}</p>}
            {!!mine.length && <Section title={t('appr.mine')} bare action={<Badge tone="selected">{mine.length}</Badge>}><div className="grid gap-4 lg:grid-cols-2">{mine.map((r) => <Item key={r.id} r={r} />)}</div></Section>}
            {!!others.length && <Section title={t('appr.blocked')} bare action={<Badge>{others.length}</Badge>}><div className="grid gap-4 lg:grid-cols-2">{others.map((r) => <Item key={r.id} r={r} />)}</div></Section>}
          </Stack>
        )}
    </>
  );
}
