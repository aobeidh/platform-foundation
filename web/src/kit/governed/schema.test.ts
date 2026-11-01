import { describe, expect, it } from 'vitest';
import { clean, defaults, objectToZod } from './schema';

const schema = { type: 'object', required: ['base_url'], properties: {
  base_url: { type: 'string', format: 'uri' }, timeout_ms: { type: 'integer', minimum: 100, maximum: 30000, default: 5000 },
  method: { type: 'string', enum: ['POST', 'PUT'] }, compress: { type: 'boolean' },
} };

describe('JSON Schema to zod', () => {
  it('validates what plugin descriptors declare, with translation keys as messages', () => {
    const z = objectToZod(schema);
    expect(z.safeParse({ base_url: 'https://a.example', timeout_ms: '800', method: 'POST', compress: true }).success).toBe(true);
    const bad = z.safeParse({ base_url: 'http://a', timeout_ms: '5', method: 'GET', compress: false });
    expect(bad.success).toBe(false);
    const messages = bad.error!.issues.map((i) => i.message.split('|')[0]).sort();
    expect(messages).toEqual(['form.err.choose', 'form.err.range', 'form.err.url']);
  });

  it('starts from declared defaults and drops empty optional values', () => {
    expect(defaults(schema)).toEqual({ base_url: '', timeout_ms: 5000, method: 'POST', compress: false });
    expect(clean(schema, { base_url: 'https://a', timeout_ms: '700', method: '', compress: false })).toEqual({ base_url: 'https://a', timeout_ms: 700, compress: false });
  });
});
