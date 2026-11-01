import { asProblem, type ApiRequest, type ApiResponse, type Transport } from './transport';

/** Calls a real platform service. Same origin by default (the dev server proxies /api). */
export class HttpTransport implements Transport {
  readonly kind = 'http' as const;
  constructor(private readonly baseUrl = '') {}

  async send(req: ApiRequest): Promise<ApiResponse> {
    let res: Response;
    try {
      res = await fetch(this.baseUrl + req.path, {
        method: req.method,
        headers: { Accept: 'application/json', ...(req.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...req.headers },
        body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
      });
    } catch {
      return { status: 0, headers: {}, body: asProblem(0, null) };
    }
    const headers: Record<string, string> = {};
    res.headers.forEach((v, k) => { headers[k.toLowerCase()] = v; });
    const text = await res.text();
    let body: unknown = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    return { status: res.status, headers, body };
  }
}

/** True when a platform service answers its liveness probe on this origin. */
export async function serviceIsReachable(baseUrl = ''): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 1500);
    const r = await fetch(`${baseUrl}/health/live`, { signal: ctrl.signal });
    clearTimeout(timer);
    return r.ok;
  } catch {
    return false;
  }
}
