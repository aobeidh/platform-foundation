import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { FlaskConical, Menu, Search, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/ui/atoms/button';
import { Kbd } from '@/ui/atoms/misc';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/ui/atoms/sheet';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/ui/atoms/tooltip';
import { NavItem } from '@/ui/molecules/nav-item';
import { cn } from '@/lib/utils';
import { usePrefs } from '@/lib/prefs';

export interface NavEntry { to: string; label: string; icon: React.ReactNode; count?: number; end?: boolean }
export interface NavGroup { label: string; items: NavEntry[] }
export interface Stage { id: string; label: string }

/** A 28 px strip that says plainly what is real and what is simulated. */
export function DemoBanner({ children, end }: { children: React.ReactNode; end?: React.ReactNode }) {
  return (
    <div className="flex h-7 items-center gap-2 bg-banner px-4 text-12 font-medium text-banner-fg">
      <FlaskConical className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{children}</span>
      {end && <span className="ms-auto hidden shrink-0 items-center gap-2 sm:flex">{end}</span>}
    </div>
  );
}

export function TopBar({ product, links, onSearch, onMenu, actions }: {
  product: string; links: NavEntry[]; onSearch: () => void; onMenu: () => void; actions: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex h-[46px] items-center gap-2 bg-card px-3 shadow-[0_1px_0_var(--line)] sm:px-4">
      <Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label={t('shell.menu')} onClick={onMenu}><Menu /></Button>
      <NavLink to="/" className="flex items-center gap-2 rounded-[8px] pe-2 focus-visible:outline-2 focus-visible:outline-accent">
        <span aria-hidden className="grid size-7 place-items-center rounded-[8px] bg-gradient-to-br from-accent to-accent2 text-[13px] font-bold text-on-accent">P</span>
        <span className="hidden text-14 font-semibold tracking-tight text-fg sm:inline">{product}</span>
      </NavLink>
      <nav aria-label={product} className="ms-2 hidden items-center gap-1 md:flex">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}
            className={({ isActive }) => cn('relative flex h-9 items-center rounded-lg px-3 text-[13.5px] font-medium transition',
              isActive ? 'text-fg after:absolute after:inset-x-3 after:-bottom-[5px] after:h-0.5 after:rounded-full after:bg-accent' : 'text-muted hover:text-fg')}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <div className="ms-auto flex items-center gap-1">
        <button type="button" onClick={onSearch}
          className="hidden h-8 w-56 items-center gap-2 rounded-[10px] border border-line2 bg-panel px-2.5 text-13 text-dim transition hover:border-accent/50 lg:flex">
          <Search className="size-4" aria-hidden /><span className="truncate">{t('shell.search')}</span><Kbd className="ms-auto">Ctrl K</Kbd>
        </button>
        <Tooltip>
          <TooltipTrigger asChild><Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label={t('shell.search')} onClick={onSearch}><Search /></Button></TooltipTrigger>
          <TooltipContent>{t('shell.search')}</TooltipContent>
        </Tooltip>
        {actions}
      </div>
    </div>
  );
}

export function LifecycleRail({ stages, current, label }: { stages: Stage[]; current?: string; label: string }) {
  return (
    <nav aria-label={label} className="h-[26px] overflow-x-auto border-b border-line bg-bg1 px-4">
      <ol className="mx-auto flex h-full max-w-[1400px] items-center gap-4 whitespace-nowrap text-12">
        {stages.map((s, i) => (
          <li key={s.id} aria-current={s.id === current ? 'step' : undefined} data-stage={s.id}
            className={cn('flex items-center gap-1.5 leading-none', s.id === current ? 'font-semibold text-accent' : 'text-dim')}>
            <span className={cn('num grid size-4 place-items-center rounded-full text-[10px] leading-none', s.id === current ? 'bg-accent text-on-accent' : 'bg-panel2 text-muted')}>{i + 1}</span>
            {s.label}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function NavGroups({ groups, onNavigate }: { groups: NavGroup[]; onNavigate?: () => void }) {
  return (
    <div className="flex flex-col gap-5">
      {groups.map((g) => (
        <div key={g.label}>
          <div className="eyebrow mb-1.5 px-3">{g.label}</div>
          <div className="flex flex-col gap-0.5">{g.items.map((i) => <NavItem key={i.to} {...i} onNavigate={onNavigate} />)}</div>
        </div>
      ))}
    </div>
  );
}

export function SideNav({ groups, label }: { groups: NavGroup[]; label: string }) {
  return (
    <aside aria-label={label} className="no-print sticky top-[var(--shell-top)] hidden h-[calc(100vh-var(--shell-top))] w-60 shrink-0 overflow-y-auto py-6 pe-4 lg:block">
      <NavGroups groups={groups} />
    </aside>
  );
}

export function MobileNav({ groups, open, onOpenChange, title }: { groups: NavGroup[]; open: boolean; onOpenChange: (o: boolean) => void; title: string }) {
  const { dir } = usePrefs();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={dir === 'rtl' ? 'right' : 'left'} className="glass-strong w-72 max-w-[85vw] rounded-none p-4">
        <SheetHeader className="p-0 pb-3"><SheetTitle>{title}</SheetTitle><SheetDescription className="sr-only">{title}</SheetDescription></SheetHeader>
        <NavGroups groups={groups} onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  );
}

export function AssistantButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className="no-print fixed bottom-5 start-5 z-30 flex items-center gap-2">
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button type="button" aria-label={t('shell.assistant')} onClick={() => setOpen(true)}
            className="grid size-11 place-items-center rounded-full bg-gradient-to-br from-accent to-accent2 text-on-accent shadow-(--shadow-pop) transition hover:-translate-y-px">
            <Sparkles className="size-5" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">{t('shell.assistantSoon')}</TooltipContent>
      </Tooltip>
    </div>
  );
}
