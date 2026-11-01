import { useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useApi } from '@/kit/api';
import { Avatar, AvatarFallback } from '@/ui/atoms/avatar';
import { Popover, PopoverContent, PopoverTrigger } from '@/ui/atoms/popover';
import { cn } from '@/lib/utils';

const initials = (n: string) => n.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase();

/** Switch the demo identity. Only shown while identity is a simulated provider. */
export function IdentitySwitcher() {
  const { t } = useTranslation();
  const { identity, identities, setIdentity } = useApi();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" aria-label={`${t('shell.identity')}: ${identity.displayName}`}
          className="flex h-8 items-center gap-2 rounded-[10px] px-1.5 text-start transition hover:bg-panel2 focus-visible:outline-2 focus-visible:outline-accent">
          <Avatar className="size-6"><AvatarFallback className="bg-accent/15 text-[10px] font-semibold text-accent">{initials(identity.displayName)}</AvatarFallback></Avatar>
          <span className="hidden min-w-0 flex-col leading-tight xl:flex">
            <span className="truncate text-12 font-medium text-fg">{identity.displayName}</span>
            <span className="truncate text-11 text-dim">{t(identity.roleKey)}</span>
          </span>
          <ChevronsUpDown className="hidden size-3.5 text-dim xl:block" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="glass-strong w-80 p-2">
        <div className="px-2 pb-2 pt-1">
          <div className="eyebrow">{t('shell.identity')}</div>
          <p className="mt-1 text-12 text-muted">{t('shell.identityHint')}</p>
        </div>
        <ul className="flex flex-col gap-0.5">
          {identities.map((i) => (
            <li key={i.id}>
              <button type="button" onClick={() => { setIdentity(i.id); setOpen(false); }} aria-pressed={i.id === identity.id}
                className={cn('flex w-full items-center gap-2.5 rounded-[8px] px-2 py-2 text-start transition hover:bg-panel2', i.id === identity.id && 'bg-wash')}>
                <Avatar className="size-7"><AvatarFallback className="bg-panel2 text-11 font-semibold text-muted">{initials(i.displayName)}</AvatarFallback></Avatar>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-13 font-medium text-fg">{i.displayName}</span>
                  <span className="block truncate text-12 text-dim">{t(i.roleKey)} · {i.tenant ? `${t('shell.tenant')} ${i.tenant}` : t('shell.platformScope')}</span>
                </span>
                {i.id === identity.id && <Check className="size-4 text-accent" aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
