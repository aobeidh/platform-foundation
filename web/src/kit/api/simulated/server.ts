import Ajv from 'ajv';
import type { ApiRequest, ApiResponse, Transport } from '../transport';
import type {
  Activation, Check, FieldProblem, GovernedRecord, KindInfo, Kinds, Operation, PluginInfo, Problem, RecordStatus, VersionView,
} from '../types';

// A simulated provider of the platform API. It follows the kernel's rules (lifecycle, maker-checker, separation of
// duties, revisions, tenancy, operations) closely enough that the portal cannot tell it from the exemplar service.
// The conformance test checks its answers against a journey captured from the real service. Synthetic data only.

export interface SimRole { name: string; capabilities: string[]; scope: 'tenant' | 'platform' }

export interface SimPlugin extends PluginInfo {
  /** Extra checks a real connector would run in `test` (reachability and so on). */
  test?: (config: Record<string, unknown>) => Check[];
  /** What `send` returns for one payload. */
  send?: (config: Record<string, unknown>, payload: Record<string, unknown>, now: Date) => Record<string, unknown>;
  /** Plugin-level validation after the schema, as `validate` in the SPI. */
  validate?: (config: Record<string, unknown>) => FieldProblem[];
}

export interface SimStoredRecord { record: Omit<GovernedRecord, 'current' | 'active'>; versions: VersionView[] }

export interface SimState {
  records: SimStoredRecord[];
  operations: (Operation & { tenant: string | null; input: Record<string, unknown>; done: number })[];
  activations: Activation[];
}

export interface SimSeed {
  service: string;
  capabilities: { name: string; display: Record<string, string> }[];
  roles: SimRole[];
  separationOfDuties: [string, string][];
  kinds: Kinds;
  plugins: SimPlugin[];
  /** Builds the starting data. Called once, and again on reset. */
  initial: (now: Date) => SimState;
  simulated: string[];
}

interface Caller { subject: string; roles: string[]; tenant: string | null; platform: boolean }

const STATUS: Record<string, number> = {
  VALIDATION_FAILED: 422, UNAUTHENTICATED: 401, TOKEN_INVALID: 401, FORBIDDEN: 403, NOT_FOUND: 404, REVISION_CONFLICT: 409,
  INVALID_TRANSITION: 409, MAKER_CHECKER: 403, NOT_TESTED: 409, PLUGIN_NOT_FOUND: 404, CONNECTION_NOT_ACTIVE: 409, CONFLICT: 409,
};
const TITLE: Record<string, string> = {
  VALIDATION_FAILED: 'Validation failed', UNAUTHENTICATED: 'Authentication required', TOKEN_INVALID: 'Token not valid',
  FORBIDDEN: 'Not allowed', NOT_FOUND: 'Not found', REVISION_CONFLICT: 'Revision conflict', INVALID_TRANSITION: 'Transition not allowed',
  MAKER_CHECKER: 'Second person required', NOT_TESTED: 'Test required', PLUGIN_NOT_FOUND: 'Plugin not found',
  CONNECTION_NOT_ACTIVE: 'Connection not active', CONFLICT: 'Conflict',
};

class Fail extends Error {
  constructor(public code: string, public detail: string, public errors: FieldProblem[] = []) { super(detail); }
}

/** A UUIDv7-shaped id: time ordered, like the kernel's. */
export function simId(now = Date.now(), random: () => number = Math.random) {
  const hex = now.toString(16).padStart(12, '0');
  const rand = Array.from({ length: 20 }, () => Math.floor(random() * 16).toString(16)).join('');
  const c = Math.floor(random() * 4096).toString(16).padStart(3, '0');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-7${c}-${'89ab'[Math.floor(random() * 4)]}${rand.slice(0, 3)}-${rand.slice(3, 15)}`;
}

export interface SimulatedOptions { storageKey?: string; latencyMs?: number; clock?: () => Date; persist?: boolean; stepMs?: number }

export class SimulatedTransport implements Transport {
  readonly kind = 'simulated' as const;
  private state: SimState;
  private ajv = new Ajv({ allErrors: true, strict: false });
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private listeners = new Set<() => void>();

  constructor(private readonly seed: SimSeed, private readonly opts: SimulatedOptions = {}) {
    this.state = this.load() ?? seed.initial(this.now());
    for (const op of this.state.operations) if (op.status === 'running' || op.status === 'pending') this.schedule(op.id);
  }

  /** Called whenever background work changes data, so screens can refetch. */
  subscribe(fn: () => void) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }

  reset() {
    for (const t of this.timers.values()) clearTimeout(t);
    this.timers.clear();
    this.state = this.seed.initial(this.now());
    this.save();
    this.listeners.forEach((l) => l());
  }

  private now() { return this.opts.clock?.() ?? new Date(); }

  private load(): SimState | null {
    if (this.opts.persist === false) return null;
    try {
      const raw = localStorage.getItem(this.opts.storageKey ?? 'platform-sim-v1');
      return raw ? (JSON.parse(raw) as SimState) : null;
    } catch {
      return null;
    }
  }

  private save() {
    if (this.opts.persist === false) return;
    try { localStorage.setItem(this.opts.storageKey ?? 'platform-sim-v1', JSON.stringify(this.state)); } catch { /* storage may be unavailable */ }
  }

  async send(req: ApiRequest): Promise<ApiResponse> {
    if (this.opts.latencyMs) await new Promise((r) => setTimeout(r, this.opts.latencyMs));
    const path = req.path.split('?')[0];
    const correlationId = simId();
    try {
      if (path === '/health/live') return { status: 200, headers: {}, body: { status: 'live' } };
      const caller = this.caller(req.headers?.Authorization ?? req.headers?.authorization);
      const out = this.route(req.method, path, req, caller);
      this.save();
      // A copy, never the stored object: callers (and caches) must not see later changes or change the store.
      return { ...out, body: structuredClone(out.body) };
    } catch (e) {
      const f = e instanceof Fail ? e : new Fail('INTERNAL_ERROR', 'The operation failed unexpectedly.');
      // Authentication problems come from the middleware, before routing, so they carry no instance (as in the kernel).
      const early = f.code === 'UNAUTHENTICATED' || f.code === 'TOKEN_INVALID';
      const problem: Problem = { type: 'about:blank', title: TITLE[f.code] ?? 'Internal error', status: STATUS[f.code] ?? 500,
        code: f.code, detail: f.detail, ...(early ? {} : { instance: path }), correlationId, errors: f.errors };
      return { status: problem.status, headers: { 'content-type': 'application/problem+json' }, body: problem };
    }
  }

  // Identity and policy ---------------------------------------------------------------------------------------

  private caller(auth?: string): Caller {
    if (!auth?.startsWith('Bearer ')) throw new Fail('UNAUTHENTICATED', 'Send a bearer token.');
    const parts = auth.slice(7).trim().split(':');
    if (parts.length < 3 || parts[0] !== 'demo') throw new Fail('TOKEN_INVALID', "Demo tokens look like 'demo:<subject>:<roles>[:<tenant>]'.");
    const tenant = parts[3] ? parts[3] : null;
    return { subject: parts[1], roles: parts[2].split(',').filter(Boolean), tenant, platform: tenant === null };
  }

  private raw(c: Caller) {
    const caps = new Set<string>();
    for (const name of c.roles) {
      const role = this.seed.roles.find((r) => r.name === name);
      if (!role) continue;
      if (role.scope === 'tenant' && c.tenant === null) continue;
      if (role.scope === 'platform' && c.tenant !== null) continue;
      role.capabilities.forEach((x) => caps.add(x));
    }
    return caps;
  }

  private effective(c: Caller) {
    const caps = this.raw(c);
    for (const [a, b] of this.seed.separationOfDuties) if (caps.has(a) && caps.has(b)) { caps.delete(a); caps.delete(b); }
    return caps;
  }

  private require(c: Caller, cap: string) {
    if (this.effective(c).has(cap)) return;
    const reason = this.raw(c).has(cap) ? 'withheld by a separation-of-duties rule' : 'no role grants this capability';
    throw new Fail('FORBIDDEN', `${cap}: ${reason}.`);
  }

  private visible(c: Caller, tenant: string | null) { return c.platform || tenant === c.tenant; }

  // Router -----------------------------------------------------------------------------------------------------

  private route(method: string, path: string, req: ApiRequest, c: Caller): ApiResponse {
    const ok = (body: unknown, status = 200, headers: Record<string, string> = {}) => ({ status, headers, body });
    const body = (req.body ?? {}) as Record<string, unknown>;
    const seg = path.replace(/^\/api\/v1\//, '').split('/');

    if (seg[0] === 'portal') {
      if (method !== 'GET') throw new Fail('NOT_FOUND', 'Not found.');
      if (seg[1] === 'me') {
        const caps = this.effective(c);
        return ok({ subject: c.subject, kind: 'user', tenant: c.tenant, platformScope: c.platform, roles: [...c.roles].sort(),
          onBehalfOf: null, capabilities: this.seed.capabilities.filter((x) => caps.has(x.name)).sort((a, b) => a.name.localeCompare(b.name)),
          service: this.seed.service, simulated: this.seed.simulated });
      }
      if (seg[1] === 'kinds') return ok(this.seed.kinds);
      if (seg[1] === 'plugins') {
        const items = this.seed.plugins.map(({ test: _t, send: _s, validate: _v, ...info }) => info);
        return ok({ items, total: items.length });
      }
    }

    if (seg[0] === 'operations') {
      if (seg.length === 1 && method === 'GET') {
        const items = this.state.operations.filter((o) => this.opVisible(c, o)).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
          .slice(0, 50).map((o) => this.opJson(o));
        return ok({ items, total: items.length });
      }
      const op = this.state.operations.find((o) => o.id === seg[1]);
      if (!op || !this.opVisible(c, op)) throw new Fail('NOT_FOUND', `Operation ${seg[1]} was not found.`);
      if (seg.length === 2 && method === 'GET') return ok(this.opJson(op));
      if (seg[2] === 'cancel' && method === 'POST') {
        if (!c.platform && op.createdBy !== c.subject) throw new Fail('FORBIDDEN', 'Only the person who started an operation may cancel it.');
        if (['succeeded', 'failed', 'cancelled'].includes(op.status)) throw new Fail('INVALID_TRANSITION', `Operation ${op.id} has already ${op.status}.`);
        op.cancelRequested = true; op.updatedAt = this.now().toISOString();
        return ok(this.opJson(op), 202);
      }
    }

    if (seg[0] === 'activations' && method === 'GET') {
      this.require(c, 'connections:read');
      const items = this.state.activations.filter((a) => this.visible(c, a.tenant));
      return ok({ items, total: items.length });
    }

    const kind = this.seed.kinds.items.find((k) => k.plural === seg[0]);
    if (kind) return this.governed(kind, method, seg.slice(1), body, req, c);
    throw new Fail('NOT_FOUND', `No route for ${method} ${path}.`);
  }

  // Governed records -----------------------------------------------------------------------------------------

  private view(s: SimStoredRecord): GovernedRecord {
    const current = s.versions.find((v) => v.version === s.record.currentVersion)!;
    const active = s.record.activeVersion ? s.versions.find((v) => v.version === s.record.activeVersion) ?? null : null;
    return { ...s.record, current, active };
  }

  private respond(s: SimStoredRecord, status = 200): ApiResponse {
    return { status, headers: { etag: `"${s.record.revision}"` }, body: this.view(s) };
  }

  private validateSpec(kind: KindInfo, spec: unknown): Record<string, unknown> {
    const validate = this.ajv.compile({ ...kind.schema, additionalProperties: true });
    if (!validate(spec)) {
      const errors = (validate.errors ?? []).map((e) => ({
        pointer: '/spec' + (e.instancePath || (e.params && 'missingProperty' in e.params ? `/${(e.params as { missingProperty: string }).missingProperty}` : '')),
        code: e.keyword === 'required' ? 'missing' : e.keyword, message: e.keyword === 'required' ? 'Field required' : e.message ?? 'not valid',
      }));
      throw new Fail('VALIDATION_FAILED', `The ${kind.kind} specification is not valid.`, errors);
    }
    const s = spec as Record<string, unknown>;
    const clean: Record<string, unknown> = {};
    for (const key of Object.keys(kind.schema.properties ?? {})) clean[key] = s[key] ?? (key === 'config' ? {} : undefined);
    return clean;
  }

  private revision(req: ApiRequest): number {
    const raw = req.headers?.['If-Match'] ?? req.headers?.['if-match'];
    if (!raw) throw new Fail('VALIDATION_FAILED', 'Send If-Match with the record revision.');
    const v = raw.trim().replace(/^W\//, '').replace(/"/g, '');
    if (!/^\d+$/.test(v)) throw new Fail('VALIDATION_FAILED', 'If-Match must be the record revision, like "3".');
    return Number(v);
  }

  private governed(kind: KindInfo, method: string, seg: string[], body: Record<string, unknown>, req: ApiRequest, c: Caller): ApiResponse {
    const now = this.now().toISOString();
    const caps = kind.capabilities;
    if (seg.length === 0 && method === 'GET') {
      this.require(c, caps.read);
      const items = this.state.records.filter((r) => r.record.kind === kind.kind && this.visible(c, r.record.tenant))
        .sort((a, b) => a.record.createdAt.localeCompare(b.record.createdAt)).map((r) => this.view(r));
      return { status: 200, headers: {}, body: { items, total: items.length } };
    }
    if (seg.length === 0 && method === 'POST') {
      this.require(c, caps.write);
      const spec = this.validateSpec(kind, body.spec);
      const id = simId();
      const stored: SimStoredRecord = {
        record: { id, kind: kind.kind, tenant: c.tenant, status: 'draft', revision: 1, currentVersion: 1, activeVersion: null, createdAt: now, updatedAt: now },
        versions: [{ version: 1, status: 'draft', spec, createdBy: c.subject, submittedBy: null, approvedBy: null, testResult: null,
          editedBy: [c.subject], makerChecker: kind.makerChecker !== 'never', createdAt: now }],
      };
      this.state.records.push(stored);
      return this.respond(stored, 201);
    }
    const stored = this.state.records.find((r) => r.record.kind === kind.kind && r.record.id === seg[0]);
    const product = kind.kind === 'connection' && (seg[1] === 'send' || seg[1] === 'send-batch');
    if (!product) this.require(c, method === 'GET' ? caps.read : seg[1] === 'approve' || seg[1] === 'reject' ? caps.approve : caps.write);
    if (!stored || !this.visible(c, stored.record.tenant)) throw new Fail('NOT_FOUND', `${kind.kind} ${seg[0]} was not found.`);
    if (method === 'GET' && seg.length === 1) return this.respond(stored);
    if (method === 'GET' && seg[1] === 'versions') {
      return { status: 200, headers: {}, body: { items: [...stored.versions].sort((a, b) => a.version - b.version).map((v) => ({
        version: v.version, status: v.status, spec: v.spec, createdBy: v.createdBy, submittedBy: v.submittedBy, approvedBy: v.approvedBy })) } };
    }
    if (product && method === 'POST') return this.exemplar(stored, seg[1], body, c);

    const spec = method === 'PUT' && seg[1] === 'draft' ? this.validateSpec(kind, body.spec) : null;
    const expected = this.revision(req);
    const r = stored.record;
    if (r.status === 'retired') throw new Fail('INVALID_TRANSITION', `${kind.kind} ${r.id} is retired; it cannot change.`);
    if (r.revision !== expected) throw new Fail('REVISION_CONFLICT', `${kind.kind} ${r.id} is at revision ${r.revision}, not ${expected}. Reload and try again.`);
    const cur = stored.versions.find((v) => v.version === r.currentVersion)!;
    const setStatus = (s: RecordStatus) => { r.status = s; };

    switch (method === 'PUT' ? 'draft' : seg[1]) {
      case 'draft': {
        if (cur.status === 'submitted') throw new Fail('INVALID_TRANSITION', 'The version is waiting for approval. Reject it first.');
        if (cur.status === 'draft' || cur.status === 'tested') {
          Object.assign(cur, { spec: spec!, status: 'draft', testResult: null, editedBy: cur.editedBy.includes(c.subject) ? cur.editedBy : [...cur.editedBy, c.subject] });
        } else {
          const v = r.currentVersion + 1;
          stored.versions.push({ version: v, status: 'draft', spec: spec!, createdBy: c.subject, submittedBy: null, approvedBy: null,
            testResult: null, editedBy: [c.subject], makerChecker: kind.makerChecker !== 'never', createdAt: now });
          r.currentVersion = v;
        }
        break;
      }
      case 'test': {
        if (cur.status !== 'draft' && cur.status !== 'tested') throw new Fail('INVALID_TRANSITION', `Only a draft can be tested; this one is ${cur.status}.`);
        const checks = this.runTests(cur.spec);
        cur.testResult = checks;
        cur.status = checks.every((x) => x.ok) ? 'tested' : 'draft';
        break;
      }
      case 'submit':
        if (cur.status !== 'tested') throw new Fail('NOT_TESTED', 'Run the test and fix any failed checks before submitting.');
        cur.status = 'submitted'; cur.submittedBy = c.subject;
        break;
      case 'approve': {
        if (cur.status !== 'submitted') throw new Fail('INVALID_TRANSITION', `Only a submitted version can be approved; this one is ${cur.status}.`);
        const authors = new Set([cur.createdBy, ...cur.editedBy, ...(cur.submittedBy ? [cur.submittedBy] : [])]);
        if (cur.makerChecker && authors.has(c.subject)) throw new Fail('MAKER_CHECKER', 'Someone who did not create, edit or submit this version must approve it.');
        if (r.activeVersion && r.activeVersion !== cur.version) {
          const prev = stored.versions.find((v) => v.version === r.activeVersion);
          if (prev) prev.status = 'superseded';
        }
        cur.status = 'active'; cur.approvedBy = c.subject; r.activeVersion = cur.version;
        setStatus(r.status === 'paused' ? 'paused' : 'active');
        this.state.activations.push({ connectionId: r.id, version: cur.version, tenant: r.tenant, activatedAt: now, eventId: simId() });
        break;
      }
      case 'reject':
        if (typeof body.reason !== 'string' || !body.reason) throw new Fail('VALIDATION_FAILED', 'The request is not valid.', [{ pointer: '/reason', code: 'missing', message: 'Field required' }]);
        if (cur.status !== 'submitted') throw new Fail('INVALID_TRANSITION', 'Only a submitted version can be rejected.');
        Object.assign(cur, { status: 'draft', submittedBy: null, testResult: null });
        break;
      case 'pause':
        if (r.status !== 'active') throw new Fail('INVALID_TRANSITION', `Only an active record can be paused; it is ${r.status}.`);
        setStatus('paused');
        break;
      case 'resume':
        if (r.status !== 'paused') throw new Fail('INVALID_TRANSITION', `Only a paused record can be resumed; it is ${r.status}.`);
        setStatus('active');
        break;
      case 'retire': {
        if (r.activeVersion) { const a = stored.versions.find((v) => v.version === r.activeVersion); if (a) a.status = 'retired'; }
        if (cur.version !== r.activeVersion && ['draft', 'tested', 'submitted'].includes(cur.status)) cur.status = 'retired';
        setStatus('retired');
        break;
      }
      default:
        throw new Fail('NOT_FOUND', 'Not found.');
    }
    r.revision += 1; r.updatedAt = now;
    return this.respond(stored);
  }

  private plugin(spec: Record<string, unknown>) {
    return this.seed.plugins.find((p) => p.id === spec.connector && p.version === spec.connector_version);
  }

  private runTests(spec: Record<string, unknown>): Check[] {
    const plugin = this.plugin(spec);
    if (!plugin) {
      const detail = `No connector plugin ${String(spec.connector)} ${String(spec.connector_version)} is installed.`;
      return [{ name: 'config', ok: false, detail }, { name: 'connector', ok: false, detail }];
    }
    const config = (spec.config ?? {}) as Record<string, unknown>;
    const validate = this.ajv.compile(plugin.configSchema);
    let problems: FieldProblem[] = [];
    if (!validate(config)) {
      problems = (validate.errors ?? []).map((e) => ({ pointer: e.instancePath || '', code: 'schema', message: e.message ?? 'not valid' }));
    } else if (plugin.validate) problems = plugin.validate(config);
    const configCheck: Check = problems.length
      ? { name: 'config', ok: false, detail: `The connector configuration is not valid. ${problems.map((p) => `${p.pointer}: ${p.message}`).join('; ')}`.trim() }
      : { name: 'config', ok: true, detail: "The configuration matches the connector's schema." };
    return [configCheck, ...(plugin.test?.(config) ?? [{ name: 'reach', ok: true, detail: 'The connector answered.' }])];
  }

  // Exemplar product endpoints ---------------------------------------------------------------------------------

  private activeSpec(stored: SimStoredRecord) {
    const r = stored.record;
    if (r.status !== 'active' || !r.activeVersion) return null;
    return stored.versions.find((v) => v.version === r.activeVersion)?.spec ?? null;
  }

  private sendOne(stored: SimStoredRecord, payload: Record<string, unknown>) {
    const spec = this.activeSpec(stored);
    if (!spec) throw new Fail('CONNECTION_NOT_ACTIVE', `Connection ${stored.record.id} is not active.`);
    const plugin = this.plugin(spec);
    if (!plugin) throw new Fail('PLUGIN_NOT_FOUND', `No connector plugin ${String(spec.connector)} is installed.`);
    return plugin.send?.((spec.config ?? {}) as Record<string, unknown>, payload, this.now()) ?? { accepted: true, at: this.now().toISOString() };
  }

  private exemplar(stored: SimStoredRecord, action: string, body: Record<string, unknown>, c: Caller): ApiResponse {
    this.require(c, 'connections:use');
    if (action === 'send') return { status: 200, headers: {}, body: { result: this.sendOne(stored, (body.payload ?? {}) as Record<string, unknown>) } };
    const payloads = Array.isArray(body.payloads) ? (body.payloads as Record<string, unknown>[]) : [];
    const now = this.now().toISOString();
    const op = { id: simId(), kind: 'connections.send-batch', status: 'pending' as const, progress: 0, result: null, error: null,
      cancelRequested: false, createdBy: c.subject, createdAt: now, updatedAt: now, tenant: c.tenant,
      input: { id: stored.record.id, payloads }, done: 0 };
    this.state.operations.push(op);
    this.schedule(op.id);
    return { status: 202, headers: { location: `/api/v1/operations/${op.id}` }, body: this.opJson(op) };
  }

  // Operations ---------------------------------------------------------------------------------------------------

  private opVisible(c: Caller, o: SimState['operations'][number]) {
    if (c.platform) return true;
    return o.tenant === c.tenant && (o.createdBy === c.subject || c.roles.includes('operations.read'));
  }

  private opJson(o: SimState['operations'][number]): Operation {
    const { tenant: _t, input: _i, done: _d, ...rest } = o;
    return rest;
  }

  /** Advances a send-batch operation one payload at a time, the way the exemplar's handler does. */
  private schedule(id: string) {
    const step = () => {
      const op = this.state.operations.find((o) => o.id === id);
      if (!op) return;
      const at = this.now().toISOString();
      const finish = (status: Operation['status'], patch: Partial<Operation>) => {
        Object.assign(op, { status, updatedAt: at, ...patch });
        this.timers.delete(id);
      };
      const payloads = (op.input.payloads ?? []) as Record<string, unknown>[];
      if (op.cancelRequested) finish('cancelled', { error: { code: 'CANCELLED', detail: 'The operation was cancelled.' } });
      else {
        op.status = 'running';
        const stored = this.state.records.find((r) => r.record.id === op.input.id);
        try {
          if (!stored) throw new Fail('NOT_FOUND', 'Connection not found.');
          if (op.done < payloads.length) { this.sendOne(stored, payloads[op.done]); op.done += 1; }
          op.progress = payloads.length ? Math.round((100 * op.done) / payloads.length) : 100;
          op.updatedAt = at;
          if (op.done >= payloads.length) finish('succeeded', { progress: 100, result: { sent: payloads.length } });
        } catch (e) {
          const f = e instanceof Fail ? e : new Fail('INTERNAL_ERROR', 'The operation failed unexpectedly.');
          finish('failed', { error: { code: f.code, detail: f.detail } });
        }
      }
      this.save();
      this.listeners.forEach((l) => l());
      if (op.status === 'running' || op.status === 'pending') this.timers.set(id, setTimeout(step, this.opts.stepMs ?? 450));
    };
    this.timers.set(id, setTimeout(step, this.opts.stepMs ?? 450));
  }
}
