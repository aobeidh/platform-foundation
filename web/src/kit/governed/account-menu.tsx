import { useState } from 'react';
import { ChevronsUpDown, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useApi, useMe } from '@/kit/api';
import { Avatar, AvatarFallback } from '@/ui/atoms/avatar';
import { Button } from '@/ui/atoms/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/ui/atoms/popover';

const initials = (n: string) => n.split(/[\s.@_-]+/).filter(Boolean).map((p) => p[0]).join('').slice(0, 2).toUpperCase();

/** The person signed in through the identity provider: who they are, their scope and roles, and signing out. */
export function AccountMenu() {
  const { t } = useTranslation();
  const { account, signOut } = useApi();
  const me = useMe();
  const [open, setOpen] = useState(false);
  if (!account) return null;  // demo identities: see IdentitySwitcher
  const scope = me.data ? (me.data.tenant ? `${t('shell.tenant')} ${me.data.tenant}` : t('shell.platformScope')) : '';
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" aria-label={`${t('account.label')}: ${account.name}`}
          className="flex h-8 items-center gap-2 rounded-[10px] px-1.5 text-start transition hover:bg-panel2 focus-visible:outline-2 focus-visible:outline-accent">
          <Avatar className="size-6"><AvatarFallback className="bg-accent/15 text-[10px] font-semibold text-accent">{initials(account.name)}</AvatarFallback></Avatar>
          <span className="hidden min-w-0 flex-col leading-tight xl:flex">
            <span className="truncate text-12 font-medium text-fg">{account.name}</span>
            <span className="truncate text-11 text-dim">{scope}</span>
          </span>
          <ChevronsUpDown className="hidden size-3.5 text-dim xl:block" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="glass-strong w-72 p-3">
        <div className="flex flex-col gap-1">
          <div className="eyebrow">{t('account.label')}</div>
          <p className="text-14 font-medium text-fg">{account.name}</p>
          {account.email && <p className="text-12 text-muted" dir="ltr">{account.email}</p>}
          {scope && <p className="text-12 text-dim">{scope}</p>}
          {me.data && me.data.roles.length > 0 && (
            <p className="text-12 text-dim">{t('account.roles')}: <span dir="ltr" className="font-mono">{me.data.roles.join(', ')}</span></p>
          )}
        </div>
        {signOut && (
          <div className="mt-3 border-t border-line pt-3">
            <Button variant="secondary" size="sm" className="w-full" onClick={signOut}><LogOut />{t('account.signOut')}</Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Shown instead of the portal when sign-in could not complete, or the service offers no way to sign in here. */
export function SignInProblem({ reason, onRetry }: { reason: string | null; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <div className="glass flex max-w-md flex-col gap-3 p-6" role="alert">
        <h1 className="text-18 font-semibold text-fg">{reason ? t('account.failed') : t('account.none')}</h1>
        <p className="text-13 text-muted">{reason ?? t('account.none.d')}</p>
        {onRetry && <div><Button onClick={onRetry}>{t('account.retry')}</Button></div>}
      </div>
    </main>
  );
}
