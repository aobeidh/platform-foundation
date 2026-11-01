import { z } from 'zod';
import type { JsonSchema } from '@/kit/api';

// JSON Schema (from /portal/kinds and plugin descriptors) to zod, for the subset descriptors use: strings with
// lengths, uri format and enums, integers and numbers with ranges, booleans. Messages are translation keys with
// their parameters encoded as "key|json", decoded by translateError.

const msg = (key: string, params?: Record<string, unknown>) => (params ? `${key}|${JSON.stringify(params)}` : key);

export function fieldToZod(s: JsonSchema, required: boolean): z.ZodTypeAny {
  const type = Array.isArray(s.type) ? s.type[0] : s.type;
  let out: z.ZodTypeAny;
  if (s.enum) {
    const values = s.enum.map(String) as [string, ...string[]];
    out = z.string({ required_error: msg('form.err.choose') }).refine((v) => values.includes(v), msg('form.err.choose'));
  } else if (type === 'boolean') {
    out = z.boolean();
  } else if (type === 'integer' || type === 'number') {
    let n = z.coerce.number({ invalid_type_error: msg('form.err.number') });
    if (type === 'integer') n = n.int(msg('form.err.number'));
    if (s.minimum !== undefined || s.maximum !== undefined) {
      const range = { min: s.minimum ?? '−∞', max: s.maximum ?? '∞' };
      if (s.minimum !== undefined) n = n.min(s.minimum, msg('form.err.range', range));
      if (s.maximum !== undefined) n = n.max(s.maximum, msg('form.err.range', range));
    }
    out = n;
  } else if (type === 'string') {
    let str = z.string();
    if (required) str = str.min(1, msg('form.err.required'));
    if (s.minLength && s.minLength > 1) str = str.min(s.minLength, msg('form.err.min', { n: s.minLength }));
    if (s.maxLength) str = str.max(s.maxLength, msg('form.err.max', { n: s.maxLength }));
    if (s.format === 'uri') str = str.regex(/^https:\/\/[^\s]+$/, msg('form.err.url'));
    out = str;
  } else {
    out = z.any();
  }
  if (!required) {
    if (type === 'string' && !s.enum) return out.optional().or(z.literal(''));
    if (type === 'integer' || type === 'number') return z.preprocess((v) => (v === '' || v === null ? undefined : v), out.optional());
    return out.optional();
  }
  return out;
}

export function objectToZod(schema: JsonSchema) {
  const req = new Set(schema.required ?? []);
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const [key, prop] of Object.entries(schema.properties ?? {})) shape[key] = fieldToZod(prop, req.has(key));
  return z.object(shape);
}

/** Defaults for a schema's fields, so a fresh form starts with what the plugin declares. */
export function defaults(schema: JsonSchema): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const type = Array.isArray(prop.type) ? prop.type[0] : prop.type;
    out[key] = prop.default ?? (type === 'boolean' ? false : prop.enum ? String(prop.enum[0]) : '');
  }
  return out;
}

/** Drops empty optional values before sending, so the service sees what the user actually set. */
export function clean(schema: JsonSchema, values: Record<string, unknown>) {
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const v = values[key];
    if (v === '' || v === undefined || v === null) continue;
    const type = Array.isArray(prop.type) ? prop.type[0] : prop.type;
    out[key] = type === 'integer' || type === 'number' ? Number(v) : v;
  }
  return out;
}

export function translateError(t: (k: string, o?: Record<string, unknown>) => string, raw: string) {
  const [key, json] = raw.split('|');
  return t(key, json ? JSON.parse(json) : undefined);
}

/** A readable label for a schema property: its title, or the key in sentence case. */
export function labelFor(key: string, s: JsonSchema) {
  const base = s.title ?? key.replace(/_/g, ' ');
  return base.charAt(0).toUpperCase() + base.slice(1).toLowerCase().replace(/\burl\b/g, 'URL').replace(/\bms\b/g, 'ms');
}
