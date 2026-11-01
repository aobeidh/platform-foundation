import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CommandPalette, type CommandGroupDef } from '@/ui/organisms/command-palette';
import { AssistantButton, LifecycleRail, MobileNav, SideNav, TopBar, type NavEntry, type NavGroup, type Stage } from '@/ui/organisms/shell';

export interface AppShellProps {
  product: string; banner: React.ReactNode; links: NavEntry[]; groups: NavGroup[]; stages: Stage[]; currentStage?: string;
  actions: React.ReactNode; commands: CommandGroupDef[]; children: React.ReactNode;
}

/** Banner, top bar and lifecycle rail in one fixed header (100 px), then side navigation and the page. */
export function AppShell({ product, banner, links, groups, stages, currentStage, actions, commands, children }: AppShellProps) {
  const { t } = useTranslation();
  const [menu, setMenu] = useState(false);
  const [palette, setPalette] = useState(false);
  return (
    <div className="min-h-screen bg-bg">
      <a href="#main" className="sr-only z-50 rounded-[8px] bg-card px-3 py-2 focus:not-sr-only focus:fixed focus:start-3 focus:top-3">{t('shell.skip')}</a>
      <header className="no-print fixed inset-x-0 top-0 z-40">
        {banner}
        <TopBar product={product} links={links} onSearch={() => setPalette(true)} onMenu={() => setMenu(true)} actions={actions} />
        <LifecycleRail stages={stages} current={currentStage} label={t('stage.rail')} />
      </header>
      <div className="mx-auto flex max-w-[1400px] gap-2 px-4 pt-[var(--shell-top)] sm:px-6">
        <SideNav groups={groups} label={product} />
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 pb-24 pt-7 outline-none">{children}</main>
      </div>
      <MobileNav groups={groups} open={menu} onOpenChange={setMenu} title={product} />
      <CommandPalette open={palette} onOpenChange={setPalette} groups={commands} />
      <AssistantButton />
    </div>
  );
}
