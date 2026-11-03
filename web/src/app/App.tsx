import { useMemo } from 'react';
import { HashRouter, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { Activity, Boxes, CheckCheck, Gauge, Languages, Moon, Palette, Plug, RotateCcw, ShieldCheck, Sun, Workflow, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useApi, useCan, useMe, useOperations, useRecords, type Connection } from '@/kit/api';
import { AccountMenu, IdentitySwitcher } from '@/kit/governed';
import { Button } from '@/ui/atoms/button';
import { CountBadge } from '@/ui/atoms/misc';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/ui/atoms/tooltip';
import { DemoBanner } from '@/ui/organisms/shell';
import { AppShell } from '@/ui/templates/app-shell';
import type { CommandGroupDef } from '@/ui/organisms/command-palette';
import { usePrefs } from '@/lib/prefs';
import { StageProvider, useStage } from './stage';
import { OverviewPage } from '@/pages/overview';
import { ConnectionsPage } from '@/pages/connections';
import { ConnectionDetailPage } from '@/pages/connection-detail';
import { ApprovalsPage } from '@/pages/approvals';
import { OperationsPage } from '@/pages/operations';
import { ActivationsPage } from '@/pages/activations';
import { PluginsPage } from '@/pages/plugins';
import { AccessPage } from '@/pages/access';
import { DesignLabPage, labSections } from '@/pages/admin/design-lab';

function IconAction({ label, onClick, children, count }: { label: string; onClick: () => void; children: React.ReactNode; count?: number }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onClick} className="relative">
          {children}
          {!!count && <CountBadge count={count} className="absolute -end-0.5 -top-0.5" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function useApprovalCount() {
  const me = useMe();
  const can = useCan();
  const records = useRecords<Connection['current']['spec']>('connections', can('connections:read'));
  if (!me.data || !can('connections:approve')) return 0;
  return (records.data?.items ?? []).filter((r) => r.current.status === 'submitted'
    && !(r.current.makerChecker && [r.current.createdBy, ...r.current.editedBy, r.current.submittedBy].includes(me.data!.subject))).length;
}

function Shell({ children }: { children: React.ReactNode }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { theme, toggleTheme, toggleLang } = usePrefs();
  const { transport, simulated, identities, setIdentity } = useApi();
  const me = useMe();
  const can = useCan();
  const ops = useOperations();
  const records = useRecords<Connection['current']['spec']>('connections', can('connections:read'));
  const approvals = useApprovalCount();
  const running = ops.data?.items.filter((o) => o.status === 'running' || o.status === 'pending').length ?? 0;
  const stage = useStage();
  const demoIdentity = me.data?.simulated.includes('identity') ?? transport.kind === 'simulated';

  const pages = useMemo(() => [
    { to: '/', label: t('nav.overview'), icon: <Gauge />, end: true },
    { to: '/connections', label: t('nav.connections'), icon: <Plug /> },
    { to: '/approvals', label: t('nav.approvals'), icon: <CheckCheck />, count: approvals },
    { to: '/operations', label: t('nav.operations'), icon: <Activity />, count: running },
    { to: '/activations', label: t('nav.activations'), icon: <Zap /> },
    { to: '/plugins', label: t('nav.plugins'), icon: <Boxes /> },
    { to: '/access', label: t('nav.access'), icon: <ShieldCheck /> },
    { to: '/admin/design-lab', label: t('nav.designLab'), icon: <Palette /> },
  ], [t, approvals, running]);
  const byPath = (p: string) => pages.find((x) => x.to === p)!;

  const groups = [
    { label: t('grp.workspace'), items: [byPath('/'), byPath('/approvals'), byPath('/operations')] },
    { label: t('grp.integrations'), items: [byPath('/connections'), byPath('/activations')] },
    { label: t('grp.platform'), items: [byPath('/plugins'), byPath('/access'), byPath('/admin/design-lab')] },
  ];
  const links = [byPath('/'), byPath('/connections'), byPath('/approvals'), byPath('/operations'), byPath('/plugins')];
  const stages = ['draft', 'test', 'submit', 'approve', 'run', 'observe', 'change', 'retire'].map((id) => ({ id, label: t(`stage.${id}`) }));

  const commands: CommandGroupDef[] = [
    { heading: t('palette.pages'), items: pages.map((p) => ({ id: p.to, label: p.label, icon: p.icon, run: () => navigate(p.to) })) },
    { heading: t('palette.connections'), items: (records.data?.items ?? []).map((r) => ({
      id: r.id, label: r.current.spec.name, hint: `${r.current.spec.connector} · ${t(`status.${r.status}`)}`, icon: <Workflow />,
      keywords: [r.current.spec.connector], run: () => navigate(`/connections/${r.id}`) })) },
    { heading: t('palette.sections'), items: labSections(t).map((s) => ({ id: `lab-${s.id}`, label: s.title, icon: <Palette />,
      run: () => { navigate('/admin/design-lab'); setTimeout(() => document.getElementById(s.id)?.scrollIntoView({ block: 'start' }), 80); } })) },
    { heading: t('palette.actions'), items: [
      { id: 'theme', label: t('palette.theme', { mode: t(theme === 'dark' ? 'palette.light' : 'palette.dark') }), icon: theme === 'dark' ? <Sun /> : <Moon />, run: toggleTheme },
      { id: 'lang', label: t('palette.lang'), hint: t('shell.language'), icon: <Languages />, run: toggleLang },
      ...(demoIdentity ? identities.map((i) => ({ id: `as-${i.id}`, label: t('palette.actAs', { name: i.displayName }), hint: t(i.roleKey), icon: <ShieldCheck />, run: () => setIdentity(i.id) })) : []),
    ] },
  ];

  const banner = (
    <DemoBanner end={simulated ? (
      <button type="button" onClick={() => simulated.reset()} className="inline-flex items-center gap-1 underline-offset-2 hover:underline"><RotateCcw className="size-3" aria-hidden />{t('shell.banner.reset')}</button>
    ) : undefined}>
      {transport.kind === 'simulated' ? t('shell.banner.simulated') : t('shell.banner.live', { service: me.data?.service ?? '…' })}
      {me.data?.simulated.length ? <span className="hidden sm:inline"> | {t('shell.banner.providers', { list: me.data.simulated.join(', ') })}</span> : null}
    </DemoBanner>
  );

  const actions = (
    <>
      <IconAction label={t('shell.approvals')} onClick={() => navigate('/approvals')} count={approvals}><CheckCheck /></IconAction>
      <IconAction label={t('shell.operations')} onClick={() => navigate('/operations')} count={running}><Activity /></IconAction>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="sm" className="px-2 text-12" aria-label={t('shell.languageLabel')} onClick={toggleLang} lang={i18n.language === 'ar' ? 'en' : 'ar'}>{t('shell.language')}</Button>
        </TooltipTrigger>
        <TooltipContent>{t('shell.languageLabel')}</TooltipContent>
      </Tooltip>
      <IconAction label={t('shell.theme')} onClick={toggleTheme}>{theme === 'dark' ? <Sun /> : <Moon />}</IconAction>
      {demoIdentity && <IdentitySwitcher />}
      <AccountMenu />
    </>
  );

  return (
    <AppShell product={t('shell.product')} banner={banner} links={links} groups={groups} stages={stages} currentStage={stage} actions={actions} commands={commands}>
      {children}
    </AppShell>
  );
}

/** A fresh page per connection, so state from one (a running batch, a notice) never shows on another. */
function KeyedDetail() {
  const { id } = useParams();
  return <ConnectionDetailPage key={id} />;
}

export function App() {
  return (
    <HashRouter>
      <StageProvider>
        <Shell>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/connections" element={<ConnectionsPage />} />
            <Route path="/connections/:id" element={<KeyedDetail />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/activations" element={<ActivationsPage />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/access" element={<AccessPage />} />
            <Route path="/admin/design-lab" element={<DesignLabPage />} />
            <Route path="*" element={<OverviewPage />} />
          </Routes>
        </Shell>
      </StageProvider>
    </HashRouter>
  );
}
