import type { Check, DemoIdentity, Kinds, Operation, SimPlugin, SimSeed, SimState, SimStoredRecord, VersionView } from '@/kit/api';
import { simId } from '@/kit/api';

// Synthetic data for the simulated provider: plausible, internally consistent, dated around the demo clock.
// Capabilities, roles, the kind and the echo plugin are copied from the exemplar service; the other connectors are
// simulated stand-ins so the portal shows every integration style.

export const identities: DemoIdentity[] = [
  { id: 'ada', subject: 'ada', displayName: 'Ada Hassan', roles: ['integration-admin'], tenant: 't1', roleKey: 'role.integration-admin' },
  { id: 'omar', subject: 'omar', displayName: 'Omar Saleh', roles: ['integration-approver'], tenant: 't1', roleKey: 'role.integration-approver' },
  { id: 'lina', subject: 'lina', displayName: 'Lina Haddad', roles: ['platform-operator'], tenant: null, roleKey: 'role.platform-operator' },
  { id: 'max', subject: 'max', displayName: 'Max Khoury', roles: ['integration-admin', 'integration-approver'], tenant: 't1', roleKey: 'role.both' },
];

const kinds: Kinds = {
  items: [{
    kind: 'connection', plural: 'connections', display: { en: 'Connection', ar: 'اتصال' }, makerChecker: 'policy',
    schema: {
      description: 'The governed spec of a connection: which connector plugin, which version, and its configuration.',
      properties: {
        name: { maxLength: 80, minLength: 1, title: 'Name', type: 'string' },
        connector: { title: 'Connector', type: 'string' },
        connector_version: { title: 'Connector Version', type: 'string' },
        config: { additionalProperties: true, title: 'Config', type: 'object' },
      },
      required: ['name', 'connector', 'connector_version'], title: 'ConnectionSpec', type: 'object',
    },
    capabilities: { read: 'connections:read', write: 'connections:write', approve: 'connections:approve' },
    tests: ['config_valid', 'plugin_test'],
  }],
  lifecycle: {
    versionStates: ['draft', 'tested', 'submitted', 'active', 'superseded', 'retired'],
    recordStates: ['draft', 'active', 'paused', 'retired'],
    transitions: [
      { name: 'test', from: ['draft', 'tested'], to: 'tested', capability: 'write' },
      { name: 'submit', from: ['tested'], to: 'submitted', capability: 'write' },
      { name: 'approve', from: ['submitted'], to: 'active', capability: 'approve' },
      { name: 'reject', from: ['submitted'], to: 'draft', capability: 'approve', reason: true },
      { name: 'pause', record: ['active'], to: 'paused', capability: 'write' },
      { name: 'resume', record: ['paused'], to: 'active', capability: 'write' },
      { name: 'retire', record: ['draft', 'active', 'paused'], to: 'retired', capability: 'write' },
    ],
  },
};

const reach = (detail: string): Check[] => [{ name: 'reach', ok: true, detail }];

const plugins: SimPlugin[] = [
  {
    kind: 'connector', id: 'echo', version: '1.0.0', spi: '>=0.1,<1', capabilities: ['request-reply', 'sink'],
    display: { en: 'Echo', ar: 'صدى' }, publisher: 'platform-foundation', secrets: [],
    configSchema: { type: 'object', required: ['prefix'], additionalProperties: false,
      properties: { prefix: { type: 'string', minLength: 1, maxLength: 20 }, uppercase: { type: 'boolean', default: false } } },
    validate: (c) => (String(c.prefix ?? '').trim() !== String(c.prefix ?? '')
      ? [{ pointer: '/prefix', code: 'whitespace', message: 'The prefix must not start or end with spaces.' }] : []),
    test: () => reach('Echo needs no network; it is always reachable.'),
    send: (c, p, now) => {
      const text = `${String(c.prefix)}${String(p.text ?? '')}`;
      return { echo: c.uppercase ? text.toUpperCase() : text, at: now.toISOString() };
    },
  },
  {
    kind: 'connector', id: 'rest-api', version: '2.1.0', spi: '>=0.1,<1', capabilities: ['request-reply'],
    display: { en: 'REST API', ar: 'واجهة REST' }, publisher: 'platform-foundation', secrets: ['token'],
    configSchema: { type: 'object', required: ['base_url'], additionalProperties: false, properties: {
      base_url: { type: 'string', format: 'uri', title: 'Base URL', description: 'The partner API root, over https.' },
      timeout_ms: { type: 'integer', minimum: 100, maximum: 30000, default: 5000, title: 'Timeout (ms)' },
      method: { type: 'string', enum: ['POST', 'PUT'], default: 'POST', title: 'Method' },
    } },
    validate: (c) => (String(c.base_url ?? '').startsWith('https://') ? [] : [{ pointer: '/base_url', code: 'https', message: 'Use an https:// address.' }]),
    test: (c) => reach(`${String(c.base_url)} answered 200 in 84 ms.`),
    send: (_c, _p, now) => ({ status: 202, partnerReference: `PR-${now.getTime().toString(36).toUpperCase()}`, at: now.toISOString() }),
  },
  {
    kind: 'connector', id: 'sftp-drop', version: '1.4.0', spi: '>=0.1,<1', capabilities: ['file', 'sink'],
    display: { en: 'SFTP drop', ar: 'إيداع SFTP' }, publisher: 'platform-foundation', secrets: ['private_key'],
    configSchema: { type: 'object', required: ['host', 'directory'], additionalProperties: false, properties: {
      host: { type: 'string', minLength: 3, title: 'Host' },
      directory: { type: 'string', minLength: 1, title: 'Directory', default: '/inbound' },
      file_pattern: { type: 'string', title: 'File name pattern', default: '{date}-{id}.json' },
      compress: { type: 'boolean', default: true, title: 'Compress files' },
    } },
    test: (c) => [...reach(`Signed in to ${String(c.host)} and listed ${String(c.directory)}.`),
      { name: 'write', ok: true, detail: 'Wrote and removed a probe file.' }],
    send: (c, _p, now) => ({ file: `${String(c.directory)}/${now.toISOString().slice(0, 10)}-${Math.floor(Math.random() * 9999)}.json.gz`, bytes: 1824 }),
  },
  {
    kind: 'connector', id: 'event-stream', version: '1.0.0', spi: '>=0.1,<1', capabilities: ['publish', 'subscribe'],
    display: { en: 'Event stream', ar: 'تدفق الأحداث' }, publisher: 'platform-foundation', secrets: ['sasl_password'],
    configSchema: { type: 'object', required: ['topic'], additionalProperties: false, properties: {
      topic: { type: 'string', minLength: 3, title: 'Topic' },
      partition_key: { type: 'string', title: 'Partition key', default: 'subject' },
      acks: { type: 'string', enum: ['all', 'leader'], default: 'all', title: 'Acknowledgement' },
    } },
    test: (c) => reach(`Topic ${String(c.topic)} exists with 12 partitions.`),
    send: (c, _p, now) => ({ topic: c.topic, partition: Math.floor(Math.random() * 12), offset: 48120 + Math.floor(Math.random() * 400), at: now.toISOString() }),
  },
  {
    kind: 'connector', id: 'partner-webhook', version: '0.9.0', spi: '>=0.1,<1', capabilities: ['webhook', 'sink'],
    display: { en: 'Partner webhook', ar: 'خطاف الشريك' }, publisher: 'platform-foundation', secrets: ['signing_secret'],
    configSchema: { type: 'object', required: ['url'], additionalProperties: false, properties: {
      url: { type: 'string', format: 'uri', title: 'Callback URL' },
      retries: { type: 'integer', minimum: 0, maximum: 10, default: 3, title: 'Retries' },
    } },
    validate: (c) => (String(c.url ?? '').startsWith('https://') ? [] : [{ pointer: '/url', code: 'https', message: 'Use an https:// address.' }]),
    test: (c) => (String(c.url).includes('unreachable')
      ? [{ name: 'reach', ok: false, detail: `${String(c.url)} did not answer within 5 seconds.` }]
      : reach(`${String(c.url)} answered the signed probe.`)),
    send: (_c, _p, now) => ({ delivered: true, signature: 'sha256=…', at: now.toISOString() }),
  },
];

// Deterministic randomness so every visitor sees the same demo.
function rng(seed: number) {
  return () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
}

interface Plan {
  name: string; connector: string; version: string; config: Record<string, unknown>;
  status: 'draft' | 'tested' | 'submitted' | 'active' | 'paused' | 'retired' | 'failed' | 'active+draft' | 'active+submitted';
  versions: number; by: string; daysAgo: number;
}

const plans: Plan[] = [
  { name: 'Customs declarations', connector: 'rest-api', version: '2.1.0', config: { base_url: 'https://api.customs.example.sa/v2', timeout_ms: 8000, method: 'POST' }, status: 'active', versions: 5, by: 'ada', daysAgo: 29 },
  { name: 'Bonded warehouse stock feed', connector: 'event-stream', version: '1.0.0', config: { topic: 'bzms.stock.movements', partition_key: 'warehouse', acks: 'all' }, status: 'active+submitted', versions: 4, by: 'ada', daysAgo: 27 },
  { name: 'Port community events', connector: 'event-stream', version: '1.0.0', config: { topic: 'pcs.vessel.events', partition_key: 'subject', acks: 'all' }, status: 'active', versions: 3, by: 'sara', daysAgo: 25 },
  { name: 'Partner invoice drop', connector: 'sftp-drop', version: '1.4.0', config: { host: 'sftp.partner.example.com', directory: '/inbound/invoices', file_pattern: '{date}-{id}.json', compress: true }, status: 'active', versions: 3, by: 'ada', daysAgo: 22 },
  { name: 'Payment gateway callbacks', connector: 'partner-webhook', version: '0.9.0', config: { url: 'https://pay.example.sa/hooks/platform', retries: 5 }, status: 'paused', versions: 1, by: 'ada', daysAgo: 20 },
  { name: 'Excise goods register', connector: 'rest-api', version: '2.1.0', config: { base_url: 'https://excise.example.sa/api', timeout_ms: 5000, method: 'PUT' }, status: 'active+draft', versions: 3, by: 'sara', daysAgo: 18 },
  { name: 'Carrier manifests', connector: 'sftp-drop', version: '1.4.0', config: { host: 'ftp.carrier.example.net', directory: '/manifests', file_pattern: '{date}.csv', compress: false }, status: 'submitted', versions: 1, by: 'ada', daysAgo: 6 },
  { name: 'Risk engine scores', connector: 'event-stream', version: '1.0.0', config: { topic: 'risk.scores.v2', partition_key: 'declaration', acks: 'leader' }, status: 'submitted', versions: 1, by: 'sara', daysAgo: 4 },
  { name: 'Customer master sync', connector: 'rest-api', version: '2.1.0', config: { base_url: 'https://crm.example.sa/customer-360', timeout_ms: 4000, method: 'POST' }, status: 'tested', versions: 1, by: 'ada', daysAgo: 3 },
  { name: 'Legacy ERP export', connector: 'partner-webhook', version: '0.9.0', config: { url: 'https://erp-unreachable.example.local/export', retries: 3 }, status: 'failed', versions: 1, by: 'ada', daysAgo: 2 },
  { name: 'Echo test harness', connector: 'echo', version: '1.0.0', config: { prefix: 'ZATCA:', uppercase: false }, status: 'active', versions: 2, by: 'ada', daysAgo: 15 },
  { name: 'Old manifest feed', connector: 'sftp-drop', version: '1.4.0', config: { host: 'old.carrier.example.net', directory: '/out', file_pattern: '{id}.xml', compress: false }, status: 'retired', versions: 1, by: 'sara', daysAgo: 28 },
  { name: 'Licensing authority lookup', connector: 'rest-api', version: '2.1.0', config: { base_url: 'https://licensing.example.sa/v1', timeout_ms: 3000, method: 'POST' }, status: 'draft', versions: 1, by: 'ada', daysAgo: 1 },
];

const OK_CHECKS = (detail: string): Check[] => [
  { name: 'config', ok: true, detail: "The configuration matches the connector's schema." }, { name: 'reach', ok: true, detail }];

export function initialState(now: Date): SimState {
  const rand = rng(42);
  const day = 86_400_000;
  const at = (daysAgo: number, hour = 9 + Math.floor(rand() * 8)) => {
    const d = new Date(now.getTime() - daysAgo * day);
    d.setUTCHours(hour, Math.floor(rand() * 60), Math.floor(rand() * 60), 0);
    return d;
  };
  const records: SimStoredRecord[] = [];
  const activations: SimState['activations'] = [];
  const approver = () => 'omar';

  for (const p of plans) {
    const created = at(p.daysAgo);
    const id = simId(created.getTime(), rand);
    const versions: VersionView[] = [];
    const live = p.status.startsWith('active') || p.status === 'paused';
    const pending = p.status === 'active+draft' || p.status === 'active+submitted';
    const liveCount = live ? (pending ? p.versions - 1 : p.versions) : 0;
    let t = created.getTime();
    for (let v = 1; v <= p.versions; v++) {
      const vCreated = new Date(t);
      const isLive = v <= liveCount;
      const spec = { name: p.name, connector: p.connector, connector_version: p.version,
        config: v === p.versions ? p.config : { ...p.config, ...(p.connector === 'rest-api' ? { timeout_ms: 3000 } : {}) } };
      let status: VersionView['status'] = 'draft';
      let submittedBy: string | null = null; let approvedBy: string | null = null; let testResult: Check[] | null = null;
      if (isLive) {
        status = v === liveCount ? (p.status === 'retired' ? 'retired' : 'active') : 'superseded';
        submittedBy = p.by; approvedBy = approver(); testResult = OK_CHECKS('The connector answered.');
        const activated = new Date(t + (2 + rand() * 20) * 3_600_000);
        if (activated.getTime() < now.getTime()) {
          activations.push({ connectionId: id, version: v, tenant: 't1', activatedAt: activated.toISOString(), eventId: simId(activated.getTime(), rand) });
        }
      } else if (p.status === 'retired') {
        status = 'retired';
      } else {
        const s = pending ? (p.status === 'active+submitted' ? 'submitted' : 'draft') : p.status;
        if (s === 'failed') { status = 'draft'; testResult = [{ name: 'config', ok: true, detail: "The configuration matches the connector's schema." },
          { name: 'reach', ok: false, detail: `${String(p.config.url)} did not answer within 5 seconds.` }]; }
        else if (s === 'tested') { status = 'tested'; testResult = OK_CHECKS('The connector answered.'); }
        else if (s === 'submitted') { status = 'submitted'; submittedBy = p.by; testResult = OK_CHECKS('The connector answered.'); }
        else status = 'draft';
      }
      versions.push({ version: v, status, spec, createdBy: p.by, submittedBy, approvedBy, testResult, editedBy: [p.by],
        makerChecker: true, createdAt: vCreated.toISOString() });
      t += (p.daysAgo / p.versions) * day * (0.94 + rand() * 0.05);
    }
    const recordStatus = p.status === 'paused' ? 'paused' : p.status === 'retired' ? 'retired' : live ? 'active' : 'draft';
    const updated = new Date(Math.min(now.getTime() - 3_600_000, t));
    records.push({ record: { id, kind: 'connection', tenant: 't1', status: recordStatus, revision: 1 + p.versions * 3 + (p.status === 'paused' ? 1 : 0),
      currentVersion: p.versions, activeVersion: liveCount || (p.status === 'retired' ? 1 : null), createdAt: created.toISOString(), updatedAt: updated.toISOString() }, versions });
  }

  // Background work: batch sends over the last 30 days, mostly in working hours, a few failures and one cancel.
  const operations: SimState['operations'] = [];
  const activeIds = records.filter((r) => r.record.status === 'active').map((r) => r.record.id);
  for (let i = 0; i < 150; i++) {
    const daysAgo = Math.floor(rand() * 29) + 1;
    const weekday = new Date(now.getTime() - daysAgo * day).getUTCDay();
    if ((weekday === 5 || weekday === 6) && rand() < 0.7) continue; // Friday and Saturday are quiet
    const hour = 6 + Math.floor(rand() * 12);
    const start = at(daysAgo, hour);
    const n = 20 + Math.floor(rand() * 180);
    const roll = rand();
    const status: Operation['status'] = roll < 0.08 ? 'failed' : roll < 0.11 ? 'cancelled' : 'succeeded';
    const by = rand() < 0.75 ? 'ada' : 'sara';
    const sent = status === 'succeeded' ? n : Math.floor(n * rand());
    operations.push({ id: simId(start.getTime(), rand), kind: 'connections.send-batch', status, progress: status === 'succeeded' ? 100 : Math.round((100 * sent) / n),
      result: status === 'succeeded' ? { sent: n } : null,
      error: status === 'failed' ? { code: 'PLUGIN_FAILED', detail: 'The partner answered 503 three times; the batch stopped.' }
        : status === 'cancelled' ? { code: 'CANCELLED', detail: 'The operation was cancelled.' } : null,
      cancelRequested: status === 'cancelled', createdBy: by, createdAt: start.toISOString(),
      updatedAt: new Date(start.getTime() + n * 450).toISOString(), tenant: 't1',
      input: { id: activeIds[Math.floor(rand() * activeIds.length)], payloads: [] }, done: sent });
  }
  activations.sort((a, b) => a.activatedAt.localeCompare(b.activatedAt));
  return { records, operations, activations };
}

export const seed: SimSeed = {
  service: 'connections',
  capabilities: [
    { name: 'connections:read', display: { en: 'Read connections', ar: 'عرض الاتصالات' } },
    { name: 'connections:write', display: { en: 'Change connections', ar: 'تعديل الاتصالات' } },
    { name: 'connections:approve', display: { en: 'Approve connections', ar: 'اعتماد الاتصالات' } },
    { name: 'connections:use', display: { en: 'Send through connections', ar: 'الإرسال عبر الاتصالات' } },
  ],
  roles: [
    { name: 'integration-admin', capabilities: ['connections:read', 'connections:write', 'connections:use'], scope: 'tenant' },
    { name: 'integration-approver', capabilities: ['connections:read', 'connections:approve'], scope: 'tenant' },
    { name: 'platform-operator', capabilities: ['connections:read'], scope: 'platform' },
  ],
  separationOfDuties: [['connections:write', 'connections:approve']],
  kinds, plugins, initial: initialState,
  simulated: ['identity', 'persistence', 'plugin-signatures', 'secrets'],
};
