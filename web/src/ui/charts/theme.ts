import { useEffect, useState } from 'react';
import { useMountRoot } from '@/lib/mount';

export interface ChartTheme {
  text: string; dim: string; line: string; card: string; panel2: string; accent: string; bad: string; forecast: string;
  font: string; isRtl: boolean; reducedMotion: boolean; resolve: (cssColor: string) => string;
}

const probes = new WeakMap<HTMLElement, HTMLSpanElement>();
let ctx2d: CanvasRenderingContext2D | null = null;

/**
 * Canvas cannot read var(): resolve any CSS colour (var, color-mix, oklab, named) to rgba() by letting the browser
 * compute it on a hidden probe and painting that onto a 1 px canvas.
 */
function makeResolver(root: HTMLElement) {
  // One probe per root: a portal mounted in a shadow root resolves its own tokens, not the host page's.
  let probe = probes.get(root);
  if (!probe || !probe.isConnected) {
    probe = document.createElement('span');
    probe.style.display = 'none';
    root.appendChild(probe);
    probes.set(root, probe);
  }
  if (!ctx2d) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    ctx2d = canvas.getContext('2d', { willReadFrequently: true });
  }
  const el = probe;
  const cache = new Map<string, string>();
  return (c: string) => {
    if (cache.has(c)) return cache.get(c)!;
    el.style.color = '';
    el.style.color = c;
    const computed = getComputedStyle(el).color || c;
    let out = computed;
    if (ctx2d) {
      ctx2d.clearRect(0, 0, 1, 1);
      ctx2d.fillStyle = '#000';
      ctx2d.fillStyle = computed;
      ctx2d.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = ctx2d.getImageData(0, 0, 1, 1).data;
      out = `rgba(${r}, ${g}, ${b}, ${Math.round((a / 255) * 100) / 100})`;
    }
    cache.set(c, out);
    return out;
  };
}

/** The same colour with a different opacity, for gradients and bands. */
export function withAlpha(rgba: string, alpha: number) {
  const m = rgba.match(/rgba?\(([^)]+)\)/);
  if (!m) return rgba;
  const [r, g, b] = m[1].split(',').map((x) => x.trim());
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function read(root: HTMLElement): ChartTheme {
  const resolve = makeResolver(root);
  const dirOf = root.closest('[dir]')?.getAttribute('dir') ?? document.documentElement.dir;
  return {
    text: resolve('var(--fg)'), dim: resolve('var(--fg-dim)'), line: resolve('var(--line)'), card: resolve('var(--card)'),
    panel2: resolve('var(--panel-strong)'), accent: resolve('var(--accent)'), bad: resolve('var(--bad)'), forecast: resolve('var(--forecast)'),
    font: getComputedStyle(root).fontFamily, isRtl: dirOf === 'rtl',
    reducedMotion: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false, resolve,
  };
}

/** Re-resolves when the .dark class or dir on the mount root (<html> by default) changes, so charts recolour and
 * mirror without reload. */
export function useChartTheme(): ChartTheme {
  const mount = useMountRoot();
  const root = mount === document.documentElement ? document.body : mount;
  const [theme, setTheme] = useState(() => read(root));
  useEffect(() => {
    setTheme(read(root));
    const mo = new MutationObserver(() => setTheme(read(root)));
    mo.observe(mount, { attributes: true, attributeFilter: ['class', 'dir', 'data-theme'] });
    return () => mo.disconnect();
  }, [mount, root]);
  return theme;
}

/** Defaults every chart shares: font, tight grid, quiet axes, motion that plays once and then only transitions. */
export function baseOption(t: ChartTheme) {
  return {
    textStyle: { fontFamily: t.font, color: t.text },
    grid: { left: 8, right: 22, top: 12, bottom: 4, containLabel: true },
    animation: !t.reducedMotion,
    animationDuration: 900, animationEasing: 'cubicOut' as const,
    animationDurationUpdate: 450, animationEasingUpdate: 'cubicInOut' as const,
    aria: { enabled: true },
  };
}

export function categoryAxis(t: ChartTheme, data: string[], extra: Record<string, unknown> = {}) {
  return { type: 'category' as const, data, inverse: t.isRtl, boundaryGap: false, axisLine: { show: false }, axisTick: { show: false },
    axisLabel: { color: t.dim, fontSize: 11, hideOverlap: true }, ...extra };
}

export function valueAxis(t: ChartTheme, fmt: (v: number) => string, extra: Record<string, unknown> = {}) {
  return { type: 'value' as const, position: t.isRtl ? ('right' as const) : ('left' as const), axisLine: { show: false }, axisTick: { show: false },
    splitLine: { lineStyle: { color: t.line, width: 1 } },
    axisLabel: { color: t.dim, fontSize: 11, formatter: (v: number) => fmt(v) }, ...extra };
}
