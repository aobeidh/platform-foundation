import { describe, expect, it } from 'vitest';
import { SimulatedTransport } from './server';
import { seed } from '@/data/seed';

const sim = () => new SimulatedTransport(seed, { persist: false, stepMs: 1 });
const as = (sub: string, roles: string, tenant = 't1') => ({ Authorization: `Bearer demo:${sub}:${roles}:${tenant}` });
const spec = { spec: { name: 'X', connector: 'echo', connector_version: '1.0.0', config: { prefix: 'p' } } };

describe('simulated provider rules', () => {
  it('withholds both capabilities when roles would grant write and approve (separation of duties)', async () => {
    const s = sim();
    const r = await s.send({ method: 'POST', path: '/api/v1/connections', headers: as('max', 'integration-admin,integration-approver'), body: spec });
    expect(r.status).toBe(403);
    expect((r.body as { detail: string }).detail).toBe('connections:write: withheld by a separation-of-duties rule.');
  });

  it('keeps tenants apart', async () => {
    const s = sim();
    const other = await s.send({ method: 'GET', path: '/api/v1/connections', headers: as('oli', 'integration-admin', 't2') });
    expect((other.body as { total: number }).total).toBe(0);
    const staff = await s.send({ method: 'GET', path: '/api/v1/connections', headers: { Authorization: 'Bearer demo:lina:platform-operator:' } });
    expect((staff.body as { total: number }).total).toBeGreaterThan(5);
  });

  it('withdraws a pending version on retire, and refuses every change after', async () => {
    const s = sim();
    const list = (await s.send({ method: 'GET', path: '/api/v1/connections', headers: as('ada', 'integration-admin') })).body as { items: { id: string; revision: number; current: { status: string } }[] };
    const pending = list.items.find((r) => r.current.status === 'submitted')!;
    const retired = await s.send({ method: 'POST', path: `/api/v1/connections/${pending.id}/retire`, headers: { ...as('ada', 'integration-admin'), 'If-Match': `"${pending.revision}"` } });
    expect((retired.body as { status: string; current: { status: string } }).current.status).toBe('retired');
    const again = await s.send({ method: 'POST', path: `/api/v1/connections/${pending.id}/test`, headers: { ...as('ada', 'integration-admin'), 'If-Match': `"${pending.revision + 1}"` } });
    expect((again.body as { code: string }).code).toBe('RECORD_RETIRED');
  });

  it('cancels a running batch operation cooperatively', async () => {
    const s = new SimulatedTransport(seed, { persist: false, stepMs: 20 });
    const list = (await s.send({ method: 'GET', path: '/api/v1/connections', headers: as('ada', 'integration-admin') })).body as { items: { id: string; status: string }[] };
    const live = list.items.find((r) => r.status === 'active')!;
    const op = (await s.send({ method: 'POST', path: `/api/v1/connections/${live.id}/send-batch`, headers: as('ada', 'integration-admin'), body: { payloads: Array(50).fill({}) } })).body as { id: string };
    await s.send({ method: 'POST', path: `/api/v1/operations/${op.id}/cancel`, headers: as('ada', 'integration-admin') });
    await new Promise((r) => setTimeout(r, 80));
    const done = (await s.send({ method: 'GET', path: `/api/v1/operations/${op.id}`, headers: as('ada', 'integration-admin') })).body as { status: string };
    expect(done.status).toBe('cancelled');
    const other = await s.send({ method: 'GET', path: `/api/v1/operations/${op.id}`, headers: as('omar', 'integration-approver') });
    expect(other.status).toBe(404);
  });

  it('stops a batch when the connection is paused, and says how far it got', async () => {
    const s = new SimulatedTransport(seed, { persist: false, stepMs: 15 });
    const admin = as('ada', 'integration-admin');
    const list = (await s.send({ method: 'GET', path: '/api/v1/connections', headers: admin })).body as { items: { id: string; status: string; revision: number }[] };
    const live = list.items.find((r) => r.status === 'active')!;
    const op = (await s.send({ method: 'POST', path: `/api/v1/connections/${live.id}/send-batch`, headers: admin, body: { payloads: Array(20).fill({}) } })).body as { id: string };
    await new Promise((r) => setTimeout(r, 40));
    await s.send({ method: 'POST', path: `/api/v1/connections/${live.id}/pause`, headers: { ...admin, 'If-Match': `"${live.revision}"` } });
    await new Promise((r) => setTimeout(r, 60));
    const done = (await s.send({ method: 'GET', path: `/api/v1/operations/${op.id}`, headers: admin })).body as { status: string; error: { code: string; detail: string } };
    expect(done.status).toBe('failed');
    expect(done.error.code).toBe('CONNECTION_NOT_ACTIVE');
    expect(done.error.detail).toMatch(/\d+ of 20 payloads were sent\./);
  });

  it('follows the approval rule of the kind: auto activates on submit, single lets the maker approve', async () => {
    const make = (approval: 'auto' | 'single', requireTest: boolean) => new SimulatedTransport({ ...seed,
      kinds: { ...seed.kinds, items: seed.kinds.items.map((k) => ({ ...k, approval, requireTest })) },
      initial: () => ({ records: [], operations: [], activations: [] }) }, { persist: false });
    const admin = as('ada', 'integration-admin');
    const auto = make('auto', true);
    let r = (await auto.send({ method: 'POST', path: '/api/v1/connections', headers: admin, body: spec })).body as { id: string; revision: number };
    r = (await auto.send({ method: 'POST', path: `/api/v1/connections/${r.id}/test`, headers: { ...admin, 'If-Match': `"${r.revision}"` } })).body as typeof r;
    const live = (await auto.send({ method: 'POST', path: `/api/v1/connections/${r.id}/submit`, headers: { ...admin, 'If-Match': `"${r.revision}"` } })).body as { status: string; activeVersion: number };
    expect([live.status, live.activeVersion]).toEqual(['active', 1]);
    const single = make('single', false);
    const both = as('max', 'integration-admin');
    let s = (await single.send({ method: 'POST', path: '/api/v1/connections', headers: both, body: spec })).body as { id: string; revision: number; current: { status: string } };
    s = (await single.send({ method: 'POST', path: `/api/v1/connections/${s.id}/submit`, headers: { ...both, 'If-Match': `"${s.revision}"` } })).body as typeof s;
    expect(s.current.status).toBe('submitted');
  });

  it('numbers a draft after a discarded one, keeping the discarded version in history', async () => {
    const s = sim();
    const admin = as('ada', 'integration-admin');
    const h = (r: { revision: number }) => ({ ...admin, 'If-Match': `"${r.revision}"` });
    const list = (await s.send({ method: 'GET', path: '/api/v1/connections', headers: admin })).body as { items: { id: string; status: string; revision: number; current: { status: string; spec: unknown } }[] };
    const live = list.items.find((r) => r.status === 'active' && r.current.status === 'active')!;
    let r = (await s.send({ method: 'PUT', path: `/api/v1/connections/${live.id}/draft`, headers: h(live), body: { spec: live.current.spec } })).body as typeof live & { currentVersion: number };
    const first = r.currentVersion;
    r = (await s.send({ method: 'POST', path: `/api/v1/connections/${live.id}/discard`, headers: h(r) })).body as typeof r;
    r = (await s.send({ method: 'PUT', path: `/api/v1/connections/${live.id}/draft`, headers: h(r), body: { spec: live.current.spec } })).body as typeof r;
    expect(r.currentVersion).toBe(first + 1);
    const versions = (await s.send({ method: 'GET', path: `/api/v1/connections/${live.id}/versions`, headers: admin })).body as { items: { version: number; status: string }[] };
    expect(versions.items.filter((v) => v.version >= first).map((v) => v.status)).toEqual(['discarded', 'draft']);
    const tested = await s.send({ method: 'POST', path: `/api/v1/connections/${live.id}/test`, headers: h(r) });
    expect(tested.status).toBe(200);
  });
});
