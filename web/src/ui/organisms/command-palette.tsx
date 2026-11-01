import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/ui/atoms/command';

export interface CommandEntry { id: string; label: string; hint?: string; icon?: React.ReactNode; keywords?: string[]; run: () => void }
export interface CommandGroupDef { heading: string; items: CommandEntry[] }

/** Ctrl K or Cmd K. Groups come from the page level as data, because organisms do not import fixtures. */
export function CommandPalette({ open, onOpenChange, groups }: { open: boolean; onOpenChange: (o: boolean) => void; groups: CommandGroupDef[] }) {
  const { t } = useTranslation();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); onOpenChange(!open); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title={t('shell.search')} description={t('palette.placeholder')}
      className="glass-strong top-[18%] translate-y-0 sm:max-w-xl">
      <CommandInput placeholder={t('palette.placeholder')} />
      <CommandList className="max-h-[50vh]">
        <CommandEmpty>{t('palette.empty')}</CommandEmpty>
        {groups.filter((g) => g.items.length).map((g) => (
          <CommandGroup key={g.heading} heading={g.heading} className="[&_[cmdk-group-heading]]:eyebrow">
            {g.items.map((it) => (
              <CommandItem key={it.id} value={`${it.label} ${it.hint ?? ''} ${(it.keywords ?? []).join(' ')}`}
                onSelect={() => { onOpenChange(false); setTimeout(it.run, 0); }} className="gap-2.5 text-[13.5px]">
                {it.icon}
                <span className="truncate">{it.label}</span>
                {it.hint && <span className="num ms-auto truncate text-12 text-dim">{it.hint}</span>}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
