// Synthetic fixtures for the Design lab. Shares add up, totals equal their parts, dates sit near the demo clock.

export const labTraffic = [
  { id: 'rest-api', name: 'REST API', style: 'api' as const, value: 184_220 },
  { id: 'event-stream', name: 'Event stream', style: 'event' as const, value: 142_870 },
  { id: 'sftp-drop', name: 'SFTP drop', style: 'file' as const, value: 61_400 },
  { id: 'partner-webhook', name: 'Partner webhook', style: 'hook' as const, value: 38_905 },
  { id: 'echo', name: 'Echo', style: 'api' as const, value: 1_204 },
];

export const labDaily = Array.from({ length: 21 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9, 11 + i));
  const wave = Math.sin(i / 3) * 900;
  const weekend = [5, 6].includes(d.getUTCDay()) ? 0.45 : 1;
  return { date: d.toISOString().slice(0, 10), api: Math.round((6200 + wave + i * 40) * weekend), event: Math.round((4700 + wave * 0.6) * weekend), file: Math.round((2100 + (i % 4) * 160) * weekend) };
});

export const labForecast = [
  { x: 'May', actual: 312_000 }, { x: 'Jun', actual: 336_500 }, { x: 'Jul', actual: 351_200 }, { x: 'Aug', actual: 372_900 },
  { x: 'Sep', actual: 401_300 }, { x: 'Oct', actual: 428_600, forecast: 428_600, low: 428_600, high: 428_600 },
  { x: 'Nov', forecast: 452_000, low: 431_000, high: 474_000 }, { x: 'Dec', forecast: 471_000, low: 438_000, high: 507_000 },
  { x: 'Jan', forecast: 492_000, low: 446_000, high: 541_000 },
];

export const labRows = [
  { id: 'c1', name: 'Customs declarations', connector: 'rest-api@2.1.0', style: 'api' as const, status: 'active', version: 3, sent: 84_120 },
  { id: 'c2', name: 'Bonded warehouse stock feed', connector: 'event-stream@1.0.0', style: 'event' as const, status: 'submitted', version: 3, sent: 61_480 },
  { id: 'c3', name: 'Partner invoice drop', connector: 'sftp-drop@1.4.0', style: 'file' as const, status: 'active', version: 2, sent: 12_904 },
  { id: 'c4', name: 'Payment gateway callbacks', connector: 'partner-webhook@0.9.0', style: 'hook' as const, status: 'paused', version: 1, sent: 7_310 },
  { id: 'c5', name: 'Legacy ERP export', connector: 'partner-webhook@0.9.0', style: 'hook' as const, status: 'failed', version: 1, sent: 0 },
];

export const labLineage = {
  nodes: [
    { id: 'src', col: 0, typeKey: 'node.source', title: 'Customs gateway', meta: 'rest-api@2.1.0', color: 'var(--s-api)' },
    { id: 'norm', col: 1, typeKey: 'node.normalize', title: 'Declaration v4', meta: 'schema 4.2', color: 'var(--info)' },
    { id: 'map', col: 2, typeKey: 'node.map', title: 'To risk payload', meta: 'JSONata v7', color: 'var(--accent)' },
    { id: 'rule', col: 2, typeKey: 'node.rule', title: 'High-value check', meta: 'rule v3', color: 'var(--forecast)' },
    { id: 'route', col: 3, typeKey: 'node.route', title: 'Content router', meta: 'route v2', color: 'var(--warn)' },
    { id: 't1', col: 4, typeKey: 'node.target', title: 'Risk engine', meta: 'event-stream@1.0.0', color: 'var(--s-event)' },
    { id: 't2', col: 4, typeKey: 'node.target', title: 'Archive drop', meta: 'sftp-drop@1.4.0', color: 'var(--s-file)' },
  ],
  edges: [{ from: 'src', to: 'norm' }, { from: 'norm', to: 'map' }, { from: 'norm', to: 'rule' }, { from: 'map', to: 'route' },
    { from: 'rule', to: 'route' }, { from: 'route', to: 't1' }, { from: 'route', to: 't2' }],
};
