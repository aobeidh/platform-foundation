import { useState } from 'react';
import { Archive, CheckCircle2, FlaskConical, Pause, Play, Send, Trash2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useCan, useMe, useTransition, type GovernedRecord, type KindInfo, type Transition } from '@/kit/api';
import { Button } from '@/ui/atoms/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/ui/atoms/dialog';
import { Textarea } from '@/ui/atoms/textarea';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/ui/atoms/tooltip';
import { ProblemAlert } from './problem';

const ICON: Record<Transition['name'], React.ReactNode> = {
  test: <FlaskConical />, submit: <Send />, approve: <CheckCircle2 />, reject: <XCircle />, pause: <Pause />, resume: <Play />, retire: <Archive />, discard: <Trash2 />,
};

export interface Availability { name: Transition['name']; enabled: boolean; why?: string }

/** Which lifecycle actions apply to this record now, and why each disabled one is not available. */
export function useAvailability(record: GovernedRecord<object>, kind: KindInfo): Availability[] {
  const { t } = useTranslation();
  const can = useCan();
  const me = useMe();
  const v = record.current;
  const authors = new Set([v.createdBy, ...v.editedBy, ...(v.submittedBy ? [v.submittedBy] : [])]);
  const status = t(`status.${v.status}`);
  const capOf = (n: Transition['name']) => (n === 'approve' || n === 'reject' ? kind.capabilities.approve : kind.capabilities.write);
  const pending = record.status !== 'retired' && (v.status === 'draft' || v.status === 'tested' || v.status === 'returned');
  const strict = v.makerChecker || kind.approval === 'maker_checker';
  const list: { name: Transition['name']; applies: boolean; ok: boolean; why?: string }[] = [
    { name: 'test', applies: pending, ok: true },
    { name: 'submit', applies: pending, ok: (!kind.requireTest || v.status === 'tested') && !v.testResult?.some((c) => !c.ok), why: t('act.why.state', { status }) },
    { name: 'approve', applies: v.status === 'submitted', ok: !(strict && me.data && authors.has(me.data.subject)), why: t('act.why.author') },
    { name: 'reject', applies: v.status === 'submitted', ok: true },
    { name: 'pause', applies: record.status === 'active', ok: true },
    { name: 'resume', applies: record.status === 'paused', ok: true },
    { name: 'discard', applies: pending, ok: true },
    { name: 'retire', applies: record.status !== 'retired', ok: true },
  ];
  return list.filter((a) => a.applies).map((a) => {
    const cap = capOf(a.name);
    if (!can(cap)) return { name: a.name, enabled: false, why: t('act.why.cap', { cap }) };
    return { name: a.name, enabled: a.ok, why: a.ok ? undefined : a.why };
  });
}

/** The lifecycle buttons for one record. Disabled buttons explain themselves; the API decides in the end. */
export function GovernedActions({ record, kind, onDone }: { record: GovernedRecord<object>; kind: KindInfo; onDone: (message: string, ok: boolean) => void }) {
  const { t } = useTranslation();
  const actions = useAvailability(record, kind);
  const mutation = useTransition<object>(kind.plural);
  const [dialog, setDialog] = useState<null | 'reject' | 'retire' | 'discard'>(null);
  const [reason, setReason] = useState('');
  const run = (name: Transition['name'], why?: string) => {
    mutation.mutate({ id: record.id, name, revision: record.revision, reason: why }, {
      onSuccess: (r) => {
        setDialog(null); setReason('');
        if (name === 'test') onDone(r.current.status === 'tested' ? t('act.done.test.ok') : t('act.done.test.fail'), r.current.status === 'tested');
        else if (name === 'submit' && r.current.status === 'active') onDone(t('act.done.approve.auto'), true);
        else onDone(t(`act.done.${name}`, { v: r.activeVersion }), true);
      },
    });
  };
  const primary = actions.find((a) => a.enabled && ['approve', 'submit', 'test', 'resume'].includes(a.name))?.name;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {actions.map((a) => {
          const variant = a.name === primary ? 'default' : a.name === 'retire' || a.name === 'reject' || a.name === 'discard' ? 'outline' : 'secondary';
          const button = (
            <Button key={a.name} size="sm" variant={variant} disabled={!a.enabled || mutation.isPending}
              loading={mutation.isPending && mutation.variables?.name === a.name}
              onClick={() => (a.name === 'reject' || a.name === 'retire' || a.name === 'discard' ? setDialog(a.name) : run(a.name))}>
              {ICON[a.name]}{mutation.isPending && mutation.variables?.name === a.name && a.name === 'test' ? t('act.testing') : t(`act.${a.name}`)}
            </Button>
          );
          if (a.enabled) return button;
          return (
            <Tooltip key={a.name}>
              <TooltipTrigger asChild><span tabIndex={0} className="rounded-[10px] focus-visible:outline-2 focus-visible:outline-accent">{button}</span></TooltipTrigger>
              <TooltipContent className="max-w-64">{a.why}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
      {mutation.error && !dialog && <div className="mt-3"><ProblemAlert error={mutation.error} onReload={() => { mutation.reset(); onDone('', true); }} /></div>}
      <Dialog open={dialog !== null} onOpenChange={(o) => { if (!o) { setDialog(null); mutation.reset(); } }}>
        <DialogContent className="glass-strong">
          <DialogHeader>
            <DialogTitle>{dialog === 'reject' ? t('act.reject.t', { v: record.currentVersion }) : dialog === 'discard' ? t('act.discard.t') : t('act.retire.t')}</DialogTitle>
            <DialogDescription>{dialog === 'reject' ? t('act.reject.d') : dialog === 'discard' ? t('act.discard.d') : t('act.retire.d')}</DialogDescription>
          </DialogHeader>
          {dialog === 'reject' && (
            <div className="grid gap-1.5">
              <label htmlFor="reason" className="text-13 font-medium">{t('act.reason')}</label>
              <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} aria-describedby="reason-hint" />
              <p id="reason-hint" className="text-12 text-dim">{t('act.reasonHint')}</p>
            </div>
          )}
          {mutation.error && <ProblemAlert error={mutation.error} />}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialog(null)}>{t('common.cancel')}</Button>
            {dialog === 'reject'
              ? <Button disabled={!reason.trim()} loading={mutation.isPending} onClick={() => run('reject', reason.trim())}>{t('act.reject')}</Button>
              : dialog === 'discard'
                ? <Button variant="destructive" loading={mutation.isPending} onClick={() => run('discard')}>{t('act.discard')}</Button>
                : <Button variant="destructive" loading={mutation.isPending} onClick={() => run('retire')}>{t('act.retire')}</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
