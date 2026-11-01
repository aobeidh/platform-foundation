import { describe, expect, it } from 'vitest';
import { SimulatedTransport } from '../simulated/server';
import type { ApiResponse } from '../transport';
import { seed } from '@/data/seed';
import recorded from './exemplar-journey.json';

// The simulated provider must answer the journey recorded from the real exemplar service with the same statuses and
// the same shapes (keys and value types). exemplar/service/tests/test_exemplar.py holds the service to the same file.

type Rec = Record<string, { status: number; body: unknown }>;
const ADA = { Authorization: 'Bearer demo:ada:integration-admin:t1' };
const OMAR = { Authorization: 'Bearer demo:omar:integration-approver:t1' };

function shape(v: unknown): unknown {
  if (Array.isArray(v)) return v.length ? [shape(v[0])] : [];
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map((k) => [k, shape((v as Record<string, unknown>)[k])]));
  if (v === null) return 'NoneType';
  return { string: 'str', number: Number.isInteger(v) ? 'int' : 'float', boolean: 'bool' }[typeof v as 'string'] ?? typeof v;
}

async function journey() {
  const sim = new SimulatedTransport({ ...seed, initial: () => ({ records: [], operations: [], activations: [] }) }, { persist: false, stepMs: 1 });
  const out: Rec = {};
  const call = async (key: string, method: 'GET' | 'POST', path: string, headers: Record<string, string> = {}, body?: unknown) => {
    const r: ApiResponse = await sim.send({ method, path, headers, body });
    out[key] = { status: r.status, body: r.body };
    return r.body as Record<string, unknown>;
  };
  const at = (who: Record<string, string>, rec: Record<string, unknown>) => ({ ...who, 'If-Match': `"${rec.revision}"` });
  const spec = (name: string, prefix: string) => ({ spec: { name, connector: 'echo', connector_version: '1.0.0', config: { prefix } } });
  const base = '/api/v1/connections';
  await call('me', 'GET', '/api/v1/portal/me', ADA);
  await call('kinds', 'GET', '/api/v1/portal/kinds', ADA);
  await call('plugins', 'GET', '/api/v1/portal/plugins', ADA);
  let rec = await call('created', 'POST', base, ADA, spec('Customs gateway', 'ZATCA'));
  const id = String(rec.id);
  rec = await call('tested', 'POST', `${base}/${id}/test`, at(ADA, rec));
  rec = await call('submitted', 'POST', `${base}/${id}/submit`, at(ADA, rec));
  await call('selfApprove', 'POST', `${base}/${id}/approve`, at(ADA, rec));
  await call('approved', 'POST', `${base}/${id}/approve`, at(OMAR, rec));
  await call('activations', 'GET', '/api/v1/activations', ADA);
  await call('send', 'POST', `${base}/${id}/send`, ADA, { payload: { text: 'D-1' } });
  const op = await call('accepted', 'POST', `${base}/${id}/send-batch`, ADA, { payloads: [{ n: 0 }, { n: 1 }, { n: 2 }] });
  await new Promise((r) => setTimeout(r, 60));
  await call('operation', 'GET', `/api/v1/operations/${String(op.id)}`, ADA);
  await call('operations', 'GET', '/api/v1/operations', ADA);
  await call('versions', 'GET', `${base}/${id}/versions`, ADA);
  await call('list', 'GET', base, ADA);
  await call('forbidden', 'POST', base, OMAR, spec('x', 'a'));
  const bad = (await sim.send({ method: 'POST', path: base, headers: ADA, body: spec('x', ' a') })).body as Record<string, unknown>;
  await call('failedTest', 'POST', `${base}/${String(bad.id)}/test`, at(ADA, bad));
  await call('stale', 'POST', `${base}/${id}/pause`, { ...ADA, 'If-Match': '"1"' });
  await call('invalid', 'POST', base, ADA, { spec: { name: 'x' } });
  await call('anon', 'GET', '/api/v1/portal/me');
  return out;
}

describe('simulated provider conformance with the exemplar service', async () => {
  const live = await journey();
  const real = recorded as Rec;

  it('answers every step with the recorded status', () => {
    expect(Object.fromEntries(Object.entries(live).map(([k, v]) => [k, v.status]))).toEqual(Object.fromEntries(Object.entries(real).map(([k, v]) => [k, v.status])));
  });

  for (const key of Object.keys(real)) {
    it(`matches the shape of "${key}"`, () => {
      expect(shape(live[key].body)).toEqual(shape(real[key].body));
    });
  }

  it('enforces the same rules with the same codes and wording', () => {
    const code = (k: string) => (live[k].body as { code: string }).code;
    expect([code('selfApprove'), code('forbidden'), code('stale'), code('invalid'), code('anon')]).toEqual(['FORBIDDEN', 'FORBIDDEN', 'REVISION_CONFLICT', 'VALIDATION_FAILED', 'UNAUTHENTICATED']);
    expect((live.failedTest.body as { current: { testResult: unknown } }).current.testResult).toEqual((real.failedTest.body as { current: { testResult: unknown } }).current.testResult);
    expect(live.kinds.body).toEqual(real.kinds.body);
    const echo = (b: unknown) => (b as { items: { id: string }[] }).items.find((p) => p.id === 'echo');
    expect(echo(live.plugins.body)).toEqual(echo(real.plugins.body));
    expect((live.operation.body as { result: unknown }).result).toEqual((real.operation.body as { result: unknown }).result);
  });
});
