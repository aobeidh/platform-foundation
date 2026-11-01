import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/kit/api';
import { Button } from '@/ui/atoms/button';

export function problemText(e: unknown) {
  if (e instanceof ApiError) return e.problem.detail || e.problem.title;
  return e instanceof Error ? e.message : String(e);
}

/** An API problem as the user should read it: what failed, which fields, and what to do. */
export function ProblemAlert({ error, onReload }: { error: unknown; onReload?: () => void }) {
  const { t } = useTranslation();
  if (!error) return null;
  const p = error instanceof ApiError ? error.problem : null;
  const conflict = p?.code === 'REVISION_CONFLICT';
  return (
    <div role="alert" className="flex items-start gap-3 rounded-[10px] border border-bad/30 bg-bad/8 px-3 py-2.5">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" aria-hidden />
      <div className="min-w-0 flex-1 text-13">
        <p className="font-medium text-fg">{conflict ? t('act.conflict') : problemText(error)}</p>
        {p?.errors?.length ? (
          <ul className="mt-1 list-disc ps-4 text-12 text-muted">{p.errors.map((f) => <li key={f.pointer + f.code}><code className="font-mono">{f.pointer}</code> {f.message}</li>)}</ul>
        ) : null}
        {p && <p className="mt-1 font-mono text-11 text-dim">{p.code}{p.correlationId ? ` · ${t('common.correlation', { id: p.correlationId })}` : ''}</p>}
      </div>
      {conflict && onReload && <Button size="xs" variant="secondary" onClick={onReload}>{t('common.reload')}</Button>}
    </div>
  );
}
