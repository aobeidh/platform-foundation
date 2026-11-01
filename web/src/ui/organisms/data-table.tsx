import { useMemo, useState } from 'react';
import {
  flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown, Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/ui/atoms/button';
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '@/ui/atoms/table';
import { SearchBox } from '@/ui/molecules/search-box';
import { EmptyState, ErrorState, LoadingState } from '@/ui/molecules/states';
import { cn } from '@/lib/utils';

export interface Column<T> {
  key: string; header: string; numeric?: boolean; sortable?: boolean; className?: string;
  /** The value used for sorting, searching and CSV. */
  value?: (row: T) => string | number | null | undefined;
  render?: (row: T) => React.ReactNode;
}

export interface DataTableProps<T> {
  rows: T[] | undefined; columns: Column<T>[]; rowKey: (row: T) => string; caption: string;
  query?: string; onQueryChange?: (q: string) => void; searchable?: boolean; csvName?: string;
  loading?: boolean; error?: { cause: string; correlationId?: string; onRetry?: () => void } | null;
  empty?: { title: string; description: string; action?: React.ReactNode };
  toolbar?: React.ReactNode; onRowClick?: (row: T) => void; maxHeight?: number; className?: string;
}

function csv<T>(rows: T[], cols: Column<T>[]) {
  const cell = (v: unknown) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [cols.map((c) => cell(c.header)).join(','), ...rows.map((r) => cols.map((c) => cell(c.value?.(r))).join(','))].join('\n');
}

/** A searchable, sortable table in a glass card with loading, empty and error states and CSV export. */
export function DataTable<T>({ rows, columns, rowKey, caption, query: controlled, onQueryChange, searchable = true, csvName,
  loading, error, empty, toolbar, onRowClick, maxHeight = 560, className }: DataTableProps<T>) {
  const { t } = useTranslation();
  const [own, setOwn] = useState('');
  const query = controlled ?? own;
  const setQuery = onQueryChange ?? setOwn;
  const [sorting, setSorting] = useState<SortingState>([]);
  const defs = useMemo<ColumnDef<T>[]>(() => columns.map((c) => ({
    id: c.key, header: c.header, accessorFn: (r: T) => c.value?.(r) ?? '', enableSorting: c.sortable !== false && !!c.value,
    enableGlobalFilter: !!c.value && !c.numeric, cell: (ctx) => (c.render ? c.render(ctx.row.original) : String(c.value?.(ctx.row.original) ?? '')),
    sortingFn: c.numeric ? 'basic' : 'alphanumeric',
  })), [columns]);
  const table = useReactTable({
    data: rows ?? [], columns: defs, getRowId: rowKey, state: { sorting, globalFilter: query }, onSortingChange: setSorting,
    globalFilterFn: 'includesString', getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel(),
  });
  const visible = table.getRowModel().rows;

  const download = () => {
    const blob = new Blob([csv(visible.map((r) => r.original), columns)], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `${csvName ?? 'export'}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  let body: React.ReactNode;
  if (loading) body = <LoadingState />;
  else if (error) body = <ErrorState cause={error.cause} correlationId={error.correlationId} onRetry={error.onRetry} />;
  else if (!rows?.length && empty) body = <EmptyState {...empty} />;
  else body = (
    <div className="overflow-auto" style={{ maxHeight }}>
      <Table>
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader className="sticky top-0 z-10 bg-panel2">
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id} className="border-0 hover:bg-transparent">
              {hg.headers.map((h) => {
                const col = columns.find((c) => c.key === h.column.id)!;
                const sorted = h.column.getIsSorted();
                return (
                  <TableHead key={h.id} aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    className={cn('h-auto border-b border-line px-3.5 py-2.5 text-12 font-semibold text-muted', col.numeric ? 'text-end' : 'text-start')}>
                    {h.column.getCanSort() ? (
                      <button type="button" onClick={h.column.getToggleSortingHandler()} aria-label={t('table.sort', { col: col.header })}
                        className={cn('inline-flex items-center gap-1 rounded-[6px] hover:text-fg focus-visible:outline-2 focus-visible:outline-accent', col.numeric && 'flex-row-reverse')}>
                        {col.header}
                        {sorted === 'asc' ? <ArrowUp className="size-3" /> : sorted === 'desc' ? <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-50" />}
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {visible.map((r) => (
            <TableRow key={r.id} onClick={onRowClick ? () => onRowClick(r.original) : undefined}
              className={cn('border-line hover:bg-panel2/60', onRowClick && 'cursor-pointer')}>
              {r.getVisibleCells().map((c) => {
                const col = columns.find((x) => x.key === c.column.id)!;
                return <TableCell key={c.id} className={cn('px-3.5 py-2.5 text-[13.5px] text-fg', col.numeric && 'num text-end', col.className)}>{flexRender(c.column.columnDef.cell, c.getContext())}</TableCell>;
              })}
            </TableRow>
          ))}
          {!visible.length && (
            <TableRow><TableCell colSpan={columns.length} className="py-8 text-center text-13 text-muted">{t('table.noMatch', { q: query })}</TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );

  return (
    <div className={cn('glass flex min-w-0 flex-col overflow-hidden', className)}>
      {(searchable || toolbar || csvName) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
          {searchable && <SearchBox value={query} onChange={setQuery} placeholder={t('table.search')} />}
          <div className="ms-auto flex items-center gap-2">
            {toolbar}
            {csvName && <Button variant="ghost" size="sm" onClick={download} disabled={!visible.length}><Download />{t('table.csv')}</Button>}
          </div>
        </div>
      )}
      {body}
      {!loading && !error && !!rows?.length && (
        <div className="border-t border-line px-3.5 py-2 text-12 text-dim">{t('table.rows', { count: visible.length })}</div>
      )}
    </div>
  );
}
