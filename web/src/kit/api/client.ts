import { ApiError, asProblem, type Method, type Transport } from './transport';
import type { TokenSource } from './identity';
import type {
  Activation, Connection, ConnectionSpec, GovernedRecord, Kinds, Me, Operation, Page, PluginInfo, Transition, VersionSummary,
} from './types';

export interface Sent<T> { data: T; etag?: string; location?: string; status: number }

/** Typed calls on top of the Transport port. One instance per portal, created in wiring. */
export class ApiClient {
  constructor(public readonly transport: Transport, private readonly tokens: TokenSource) {}

  async call<T>(method: Method, path: string, opts: { body?: unknown; ifMatch?: number; idempotencyKey?: string } = {}): Promise<Sent<T>> {
    const headers: Record<string, string> = {};
    const token = this.tokens.token();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (opts.ifMatch !== undefined) headers['If-Match'] = `"${opts.ifMatch}"`;
    if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;
    const res = await this.transport.send({ method, path, body: opts.body, headers });
    if (res.status < 200 || res.status >= 300) throw new ApiError(asProblem(res.status, res.body));
    return { data: res.body as T, etag: res.headers.etag, location: res.headers.location, status: res.status };
  }

  // Portal API (kernel)
  me = async () => (await this.call<Me>('GET', '/api/v1/portal/me')).data;
  kinds = async () => (await this.call<Kinds>('GET', '/api/v1/portal/kinds')).data;
  plugins = async () => (await this.call<Page<PluginInfo>>('GET', '/api/v1/portal/plugins')).data;

  // Governed records (kernel, generated per kind)
  list = async <S>(plural: string) => (await this.call<Page<GovernedRecord<S>>>('GET', `/api/v1/${plural}`)).data;
  get = async <S>(plural: string, id: string) => (await this.call<GovernedRecord<S>>('GET', `/api/v1/${plural}/${id}`)).data;
  versions = async <S>(plural: string, id: string) =>
    (await this.call<{ items: VersionSummary<S>[] }>('GET', `/api/v1/${plural}/${id}/versions`)).data.items;
  create = async <S>(plural: string, spec: S) => (await this.call<GovernedRecord<S>>('POST', `/api/v1/${plural}`, { body: { spec } })).data;
  updateDraft = async <S>(plural: string, id: string, spec: S, revision: number) =>
    (await this.call<GovernedRecord<S>>('PUT', `/api/v1/${plural}/${id}/draft`, { body: { spec }, ifMatch: revision })).data;
  transition = async <S>(plural: string, id: string, name: Transition['name'], revision: number, reason?: string) =>
    (await this.call<GovernedRecord<S>>('POST', `/api/v1/${plural}/${id}/${name}`, {
      ifMatch: revision, body: reason !== undefined ? { reason } : undefined,
    })).data;

  // Operations (kernel)
  operations = async () => (await this.call<Page<Operation>>('GET', '/api/v1/operations')).data;
  operation = async (id: string) => (await this.call<Operation>('GET', `/api/v1/operations/${id}`)).data;
  cancelOperation = async (id: string) => (await this.call<Operation>('POST', `/api/v1/operations/${id}/cancel`)).data;

  // Exemplar product endpoints
  activations = async () => (await this.call<Page<Activation>>('GET', '/api/v1/activations')).data;
  send = async (id: string, payload: Record<string, unknown>) =>
    (await this.call<{ result: Record<string, unknown> }>('POST', `/api/v1/connections/${id}/send`, {
      body: { payload }, idempotencyKey: crypto.randomUUID(),
    })).data.result;
  sendBatch = async (id: string, payloads: Record<string, unknown>[]) =>
    (await this.call<Operation>('POST', `/api/v1/connections/${id}/send-batch`, { body: { payloads } })).data;
}

export type { Connection, ConnectionSpec };
export { ApiError, asProblem };
