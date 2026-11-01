import { Mono } from '@/ui/atoms/misc';

export function PageHeader({ eyebrow, title, description, tags, actions, meta }: {
  eyebrow: string; title: React.ReactNode; description?: React.ReactNode; tags?: string[]; actions?: React.ReactNode; meta?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="min-w-0">
        <div className="eyebrow mb-2 flex items-center gap-2"><span aria-hidden className="h-0.5 w-4 rounded-full bg-accent" />{eyebrow}</div>
        <h1 className="text-26 font-semibold tracking-tight text-balance text-fg md:text-30">{title}</h1>
        {meta && <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div>}
        {description && <p className="mt-2 max-w-3xl text-[13.5px] text-muted">{description}</p>}
        {tags && <div className="mt-3 flex flex-wrap gap-1.5">{tags.map((t) => <Mono key={t}>{t}</Mono>)}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
