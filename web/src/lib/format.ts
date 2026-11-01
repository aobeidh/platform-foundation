// Locale-aware formatting. Charts, tooltips and tables all call these, so numbers read the same everywhere.
// Latin digits are kept in Arabic too (nu-latn), as most Gulf government portals do.
let locale = 'en-US';
export function setFormatLocale(lang: string) {
  locale = lang === 'ar' ? 'ar-SA-u-nu-latn' : 'en-US';
}

export const num = (v: number, digits = 0) =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const compact = (v: number) =>
  new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(v);

export const pct = (v: number, digits = 1) =>
  new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const money = (v: number, cur = 'SAR') => `${cur} ${num(v)}`;
export const compactMoney = (v: number, cur = 'SAR') => `${cur} ${compact(v)}`;

const toDate = (d: string | number | Date) => (d instanceof Date ? d : new Date(d));

export const date = (d: string | number | Date) =>
  new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(toDate(d));

export const shortDate = (d: string | number | Date) =>
  new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(toDate(d));

export const dateTime = (d: string | number | Date) =>
  new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(toDate(d));

export const time = (d: string | number | Date) =>
  new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(toDate(d));

/** "3 min ago", in the active language. */
export function relative(d: string | number | Date, now = Date.now()) {
  const s = Math.round((toDate(d).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const a = Math.abs(s);
  if (a < 60) return rtf.format(s, 'second');
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute');
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour');
  return rtf.format(Math.round(s / 86400), 'day');
}

/** Short ids for display: the last 8 characters of a UUIDv7 differ between records made the same second. */
export const shortId = (id: string) => id.slice(-8);
