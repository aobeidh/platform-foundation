import type { ChartConfig } from './echart';

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

interface P { seriesId?: string; seriesName?: string; name?: string; value?: unknown; color?: unknown; data?: unknown; marker?: string }

/** A shadcn-looking tooltip as HTML with Tailwind classes. Series whose id starts with "_" are helpers and skipped. */
export function tooltipHtml(params: P | P[], config: ChartConfig, fmt: (v: number) => string, title?: string) {
  const list = (Array.isArray(params) ? params : [params]).filter((p) => !String(p.seriesId ?? '').startsWith('_'));
  if (!list.length) return '';
  const head = title ?? list[0].name ?? '';
  const rows = list.map((p) => {
    const key = String(p.seriesId ?? p.name ?? '');
    const label = config[key]?.label ?? p.seriesName ?? p.name ?? key;
    const raw = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
    const color = typeof p.color === 'string' ? p.color : 'currentColor';
    return `<div class="flex items-center gap-2"><span class="size-2.5 shrink-0 rounded-[3px]" style="background:${esc(color)}"></span>`
      + `<span class="text-muted">${esc(typeof label === 'string' ? label : key)}</span>`
      + `<span class="num ms-auto ps-4 font-medium text-fg">${esc(typeof raw === 'number' ? fmt(raw) : raw)}</span></div>`;
  }).join('');
  return `<div class="glass-strong min-w-36 rounded-[10px] px-2.5 py-2 text-12"><div class="mb-1 font-medium text-fg">${esc(head)}</div>${rows}</div>`;
}

export const tooltipBase = { className: 'echart-tip', backgroundColor: 'transparent', borderWidth: 0, padding: 0, extraCssText: 'box-shadow:none' };
