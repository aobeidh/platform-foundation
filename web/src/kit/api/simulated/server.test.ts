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
    expect((again.body as { code: string }).code).toBe('INVALID_TRANSITION');
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
});
