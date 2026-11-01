import { useState } from 'react';
import { BarChart3, Table2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/ui/atoms/button';
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/atoms/card';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/ui/atoms/tooltip';
import { Skeleton } from '@/ui/atoms/skeleton';
import { cn } from '@/lib/utils';

export interface TableAlt { headers: string[]; rows: (string | number)[][]; numeric?: boolean[] }

/** A titled card that answers one question, with a toggle to the same data as a table. */
export function ChartCard({ title, subtitle, table, children, className, loading, action }: {
  title: string; subtitle?: string; table?: TableAlt; children: React.ReactNode; className?: string; loading?: boolean; action?: React.ReactNode;
}) {
  const { t } = useTranslation();
  const [asTable, setAsTable] = useState(false);
  const label = asTable ? t('common.showChart') : t('common.showTable');
  return (
    <Card className={cn('min-w-0', className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {subtitle && <CardDescription>{subtitle}</CardDescription>}
        {(table || action) && (
          <CardAction className="flex items-center gap-1">
            {action}
            {table && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label={label} aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
                    {asTable ? <BarChart3 /> : <Table2 />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{label}</TooltipContent>
              </Tooltip>
            )}
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="min-w-0">
        {loading ? <Skeleton className="h-[220px] w-full" /> : asTable && table ? (
          <div className="max-h-[260px] overflow-auto rounded-[10px] border border-line">
            <table className="w-full text-13">
              <thead className="sticky top-0 bg-panel2"><tr>{table.headers.map((h, i) => (
                <th key={h} className={cn('px-3 py-2 text-12 font-semibold text-muted', table.numeric?.[i] ? 'text-end' : 'text-start')}>{h}</th>))}</tr></thead>
              <tbody>{table.rows.map((r, ri) => (
                <tr key={ri} className="border-t border-line">{r.map((c, ci) => (
                  <td key={ci} className={cn('px-3 py-1.5', table.numeric?.[ci] ? 'num text-end' : 'text-start')}>{c}</td>))}</tr>))}</tbody>
            </table>
          </div>
        ) : children}
      </CardContent>
    </Card>
  );
}
