import { cn } from '@/lib/utils';

export function Section({ id, title, description, children, bare, className, action }: {
  id?: string; title: string; description?: string; children: React.ReactNode; bare?: boolean; className?: string; action?: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined} className={cn('scroll-mt-[calc(var(--shell-top)+16px)]', className)}>
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <h2 id={id ? `${id}-title` : undefined} className="text-20 font-semibold tracking-tight text-fg">{title}</h2>
          {description && <p className="mt-1 text-[13.5px] text-muted">{description}</p>}
        </div>
        {action}
      </div>
      {bare ? children : <div className="glass p-5">{children}</div>}
    </section>
  );
}

export function Stack({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('space-y-10', className)}>{children}</div>;
}

export function KpiGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

export function ChartGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('grid gap-4 lg:grid-cols-3', className)}>{children}</div>;
}
