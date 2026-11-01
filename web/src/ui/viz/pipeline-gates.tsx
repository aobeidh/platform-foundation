import { Check, CircleStop } from 'lucide-react';
import { cn } from '@/lib/utils';
import { delay, useInView } from './use-width';

export interface Gate { id: string; label: string; state: 'passed' | 'blocked' | 'pending'; reason?: string; meta?: string }

/**
 * Numbered gates on a rail. Passed gates show a check; the first blocking gate shows a stop and its reason; later
 * gates are pending. The rail is green up to the last passed gate.
 */
export function PipelineGates({ gates, ariaLabel, pendingLabel }: { gates: Gate[]; ariaLabel: string; pendingLabel: string }) {
  const [ref, inView] = useInView<HTMLOListElement>();
  const firstBlock = gates.findIndex((g) => g.state === 'blocked');
  return (
    <div className="overflow-x-auto">
      <ol ref={ref} aria-label={ariaLabel} className="flex min-w-[560px] items-start">
        {gates.map((g, i) => {
          const state = firstBlock >= 0 && i > firstBlock ? 'pending' : g.state;
          return (
            <li key={g.id} className="relative flex flex-1 flex-col items-center px-1 text-center" aria-current={state === 'blocked' ? 'step' : undefined}>
              {i > 0 && (
                <span aria-hidden className="absolute end-1/2 top-4 h-0.5 w-full -translate-y-1/2 overflow-hidden bg-line">
                  <span className={cn('block h-full', state === 'passed' ? 'bg-good' : 'bg-transparent', inView ? 'anim-grow-x' : 'anim-wait')} style={delay(i * 140 - 80)} />
                </span>
              )}
              <span className={cn('relative z-10 grid size-8 place-items-center rounded-full border-2 text-12 font-semibold',
                state === 'passed' && 'border-good bg-good text-white',
                state === 'blocked' && 'border-warn bg-card text-warn',
                state === 'pending' && 'border-line2 bg-card text-dim',
                inView ? 'anim-pop' : 'anim-wait')} style={delay(i * 140)}>
                {state === 'passed' ? <Check className="size-4" aria-hidden /> : state === 'blocked' ? <CircleStop className="size-4" aria-hidden /> : <span className="num">{i + 1}</span>}
              </span>
              <span className={cn('mt-2 text-13 font-medium', state === 'pending' ? 'text-muted' : 'text-fg')}>{g.label}</span>
              <span className={cn('mt-0.5 max-w-40 text-12', state === 'blocked' ? 'text-warn' : 'text-dim')}>
                {state === 'blocked' ? g.reason : state === 'pending' ? pendingLabel : g.meta}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
