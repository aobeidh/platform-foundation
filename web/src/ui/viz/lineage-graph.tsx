import { useMemo, useState } from 'react';
import { useMountRoot } from '@/lib/mount';
import { cn } from '@/lib/utils';
import { useInView, useWidth } from './use-width';

export interface LineageNode { id: string; col: number; title: string; meta: string; type: string; color: string }
export interface LineageEdge { from: string; to: string }

/**
 * A left-to-right DAG. Links are SVG; nodes are HTML buttons on top, so icons, focus rings and truncation work.
 * Selecting a node highlights everything upstream and downstream of it.
 */
export function LineageGraph({ nodes, edges, ariaLabel }: { nodes: LineageNode[]; edges: LineageEdge[]; ariaLabel: string }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [ref, inView] = useInView<HTMLDivElement>();
  const [selected, setSelected] = useState<string | null>(null);
  const cols = Math.max(...nodes.map((n) => n.col)) + 1;
  const gap = 28;
  const pad = 8;
  const cardW = Math.max(132, Math.min(176, (Math.max(width, 560) - pad * 2 - gap * (cols - 1)) / cols));
  const cardH = 58;
  const rowGap = 14;
  const rtl = useMountRoot().dir === 'rtl';
  const pos = useMemo(() => {
    const byCol = new Map<number, LineageNode[]>();
    nodes.forEach((n) => byCol.set(n.col, [...(byCol.get(n.col) ?? []), n]));
    const tallest = Math.max(...[...byCol.values()].map((l) => l.length));
    const h = tallest * cardH + (tallest - 1) * rowGap;
    const out = new Map<string, { x: number; y: number }>();
    const total = cols * cardW + (cols - 1) * gap + pad * 2;
    byCol.forEach((list, col) => {
      const colH = list.length * cardH + (list.length - 1) * rowGap;
      list.forEach((n, i) => {
        const x = pad + col * (cardW + gap);
        out.set(n.id, { x: rtl ? total - x - cardW : x, y: (h - colH) / 2 + i * (cardH + rowGap) });
      });
    });
    return { out, h, total };
  }, [nodes, cols, cardW, rtl]);

  const related = useMemo(() => {
    if (!selected) return null;
    const set = new Set([selected]);
    const walk = (id: string, dir: 'up' | 'down') => edges.forEach((e) => {
      const [a, b] = dir === 'up' ? [e.to, e.from] : [e.from, e.to];
      if (a === id && !set.has(b)) { set.add(b); walk(b, dir); }
    });
    walk(selected, 'up'); walk(selected, 'down');
    return set;
  }, [selected, edges]);

  return (
    <div ref={box} className="overflow-x-auto">
      <div ref={ref} role="group" aria-label={ariaLabel} className="relative" style={{ width: pos.total, height: pos.h }}>
        <svg aria-hidden width={pos.total} height={pos.h} className="absolute inset-0" style={{ direction: 'ltr' }}>
          {edges.map((e, i) => {
            const a = pos.out.get(e.from)!; const b = pos.out.get(e.to)!;
            const x1 = rtl ? a.x : a.x + cardW; const x2 = rtl ? b.x + cardW : b.x;
            const y1 = a.y + cardH / 2; const y2 = b.y + cardH / 2; const mx = (x1 + x2) / 2;
            const on = related ? related.has(e.from) && related.has(e.to) : false;
            const col = nodes.find((n) => n.id === e.from)!.col;
            return <path key={i} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none"
              stroke={on ? 'var(--accent)' : 'var(--line-strong)'} strokeWidth={on ? 2 : 1.25}
              opacity={related && !on ? 0.35 : 1} className={inView ? 'anim-fade' : 'anim-wait'} style={{ '--d': `${col * 120 + 60}ms` } as React.CSSProperties} />;
          })}
        </svg>
        {nodes.map((n) => {
          const p = pos.out.get(n.id)!;
          const dim = related && !related.has(n.id);
          return (
            <button key={n.id} type="button" onClick={() => setSelected((s) => (s === n.id ? null : n.id))} aria-pressed={selected === n.id}
              className={cn('absolute flex flex-col justify-center overflow-hidden rounded-[10px] border border-line bg-card px-3 text-start shadow-(--shadow-card) transition duration-150 hover:border-line2 focus-visible:outline-2 focus-visible:outline-accent',
                related?.has(n.id) && 'border-accent ring-1 ring-accent', dim && 'opacity-45', inView ? 'anim-fade' : 'anim-wait')}
              style={{ left: p.x, top: p.y, width: cardW, height: cardH, borderInlineStartWidth: 3, borderInlineStartColor: n.color, '--d': `${n.col * 120}ms` } as React.CSSProperties}>
              <span className="truncate text-13 font-medium text-fg">{n.title}</span>
              <span className="truncate text-12 text-dim">{n.type} · {n.meta}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
