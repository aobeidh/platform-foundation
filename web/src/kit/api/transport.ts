import type { Problem } from './types';

// The API port. Products and screens talk to a Transport; which provider runs is chosen in wiring:
// `HttpTransport` calls a real service, `SimulatedTransport` answers in the browser for demos and tests.

export type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';

export interface ApiRequest { method: Method; path: string; body?: unknown; headers?: Record<string, string> }
export interface ApiResponse { status: number; headers: Record<string, string>; body: unknown }

export interface Transport {
  readonly kind: 'http' | 'simulated';
  send(req: ApiRequest): Promise<ApiResponse>;
}

/** Every non-2xx answer becomes an ApiError carrying the problem details, never a bare status. */
export class ApiError extends Error {
  constructor(public readonly problem: Problem) {
    super(problem.detail || problem.title);
    this.name = 'ApiError';
  }
  get status() { return this.problem.status; }
  get code() { return this.problem.code; }
}

export function asProblem(status: number, body: unknown): Problem {
  if (body && typeof body === 'object' && 'code' in body) {
    const p = body as Partial<Problem>;
    return { type: 'about:blank', title: '', errors: [], ...p, status: p.status ?? status, code: p.code ?? 'INTERNAL_ERROR', detail: p.detail ?? '' } as Problem;
  }
  return { type: 'about:blank', title: 'Request failed', status, code: status === 0 ? 'DEPENDENCY_UNAVAILABLE' : 'INTERNAL_ERROR',
    detail: status === 0 ? 'The service could not be reached.' : `The service answered ${status}.`, errors: [] };
}
