import { Mono } from '@/ui/atoms/misc';

export function ColorSwatch({ name, cssVar, meaning, utility }: { name: string; cssVar: string; meaning: string; utility: string }) {
  return (
    <div className="flex items-center gap-3 rounded-[10px] border border-line bg-panel p-2.5">
      <span aria-hidden className="size-10 shrink-0 rounded-[8px] border border-line" style={{ background: `var(${cssVar})` }} />
      <div className="min-w-0">
        <div className="text-13 font-medium text-fg">{name}</div>
        <div className="text-12 text-muted">{meaning}</div>
        <Mono className="mt-1 inline-block">{utility}</Mono>
      </div>
    </div>
  );
}

export function TypeSample({ label, spec, className, sample }: { label: string; spec: string; className: string; sample: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-3 last:border-0">
      <div className="min-w-0">
        <div className="mb-1 text-12 text-dim">{label}</div>
        <div className={className}>{sample}</div>
      </div>
      <Mono className="shrink-0">{spec}</Mono>
    </div>
  );
}
