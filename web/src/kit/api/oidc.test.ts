import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { OidcTokenSource, SignInError, challengeOf, type OidcEnv } from './oidc';
import { startSession } from './session';
import type { Transport } from './transport';

const ISSUER = 'https://idp.example.com/realms/notes';
const SETTINGS = { issuer: ISSUER, clientId: 'notes-portal', scopes: ['openid', 'profile'] };
const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
const jwt = (claims: Record<string, unknown>) => `${b64({ alg: 'RS256' })}.${b64(claims)}.sig`;

/** A browser at the portal and an identity provider that answers like Keycloak. */
function world(start = 'https://portal.example.com/app/?x=1#/items/notes') {
  const store = new Map<string, string>();
  const timers: { fn: () => void; ms: number }[] = [];
  const posts: Record<string, string>[] = [];
  let href = start;
  let assigned: string | null = null;
  let answer: (form: Record<string, string>) => { status: number; body: unknown } = (form) => ({
    status: 200, body: { access_token: `at-${posts.length}`, expires_in: 300, refresh_token: `rt-${posts.length}`,
      id_token: jwt({ iss: ISSUER, aud: 'notes-portal', sub: 'u-1', name: 'Ada Lovelace', email: 'ada@example.com', nonce: form.nonce ?? stash().nonce }) },
  });
  const stash = () => JSON.parse(store.get('pf-oidc-pending') ?? '{}') as { nonce: string; state: string; verifier: string };
  let pendingNonce = '';
  const env: OidcEnv = {
    fetch: (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/.well-known/openid-configuration')) {
        return new Response(JSON.stringify({ issuer: ISSUER, authorization_endpoint: `${ISSUER}/auth`, token_endpoint: `${ISSUER}/token`,
          end_session_endpoint: `${ISSUER}/logout` }), { status: 200 });
      }
      const form = Object.fromEntries(new URLSearchParams(String(init?.body)));
      posts.push(form);
      const a = answer({ ...form, nonce: pendingNonce });
      return new Response(JSON.stringify(a.body), { status: a.status });
    }) as typeof fetch,
    storage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => { store.set(k, v); }, removeItem: (k) => { store.delete(k); } },
    get location() {
      const u = new URL(href);
      return { href, origin: u.origin, pathname: u.pathname, search: u.search, hash: u.hash, assign: (to: string) => { assigned = to; } };
    },
    replaceUrl: (to) => { href = new URL(to, href).toString(); },
    random: (n) => new Uint8Array(n).map((_, i) => (i * 7 + n) % 256),
    sha256: async (d) => new Uint8Array(createHash('sha256').update(d).digest()),
    now: () => 0,
    later: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    cancel: () => { /* kept for the assertions */ },
  };
  return {
    env, store, timers, posts,
    get assigned() { return assigned; },
    /** The provider sends the browser back with a code (or what is given). */
    back(params: Record<string, string>) {
      const s = stash();
      pendingNonce = s.nonce;
      href = `https://portal.example.com/app/?${new URLSearchParams({ state: s.state, ...params })}`;
    },
    answer(fn: typeof answer) { answer = fn; },
    get href() { return href; },
  };
}

describe('PKCE', () => {
  it('derives the challenge as RFC 7636 shows', async () => {
    const env = world().env;
    expect(await challengeOf('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk', env)).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
  });
});

describe('signing in', () => {
  it('sends the person to the provider with a PKCE challenge, then completes and goes back to the page', async () => {
    const w = world();
    void OidcTokenSource.start(SETTINGS, w.env);
    await new Promise((r) => setTimeout(r, 10));
    const to = new URL(w.assigned!);
    expect(to.origin + to.pathname).toBe(`${ISSUER}/auth`);
    const q = Object.fromEntries(to.searchParams);
    expect(q).toMatchObject({ response_type: 'code', client_id: 'notes-portal', redirect_uri: 'https://portal.example.com/app/',
      scope: 'openid profile', code_challenge_method: 'S256' });
    const pending = JSON.parse(w.store.get('pf-oidc-pending')!) as { verifier: string; state: string };
    expect(q.code_challenge).toBe(await challengeOf(pending.verifier, w.env));
    expect(q.state).toBe(pending.state);

    w.back({ code: 'c-1' });
    const source = await OidcTokenSource.start(SETTINGS, w.env);
    expect(w.posts[0]).toMatchObject({ grant_type: 'authorization_code', code: 'c-1', code_verifier: pending.verifier,
      redirect_uri: 'https://portal.example.com/app/', client_id: 'notes-portal' });
    expect(source.token()).toBe('at-1');
    expect(source.account).toEqual({ subject: 'u-1', name: 'Ada Lovelace', email: 'ada@example.com' });
    expect(w.href).toBe('https://portal.example.com/app/?x=1#/items/notes');  // the code left the address bar
    expect(w.store.size).toBe(0);  // nothing kept in the browser's storage
    expect(w.timers.at(-1)!.ms).toBe(240_000);  // renewal a minute before the five minutes are up
  });

  it('refuses an answer for another sign-in', async () => {
    const w = world();
    void OidcTokenSource.start(SETTINGS, w.env);
    await new Promise((r) => setTimeout(r, 10));
    w.back({ code: 'c-1', state: 'forged' });
    await expect(OidcTokenSource.start(SETTINGS, w.env)).rejects.toThrow(SignInError);
    expect(w.posts).toEqual([]);
  });

  it('refuses an ID token with another nonce, issuer or audience', async () => {
    for (const bad of [{ nonce: 'other' }, { iss: 'https://evil.example.com' }, { aud: 'someone-else' }]) {
      const w = world();
      void OidcTokenSource.start(SETTINGS, w.env);
      await new Promise((r) => setTimeout(r, 10));
      w.back({ code: 'c-1' });
      w.answer((form) => ({ status: 200, body: { access_token: 'at', id_token: jwt({ iss: ISSUER, aud: 'notes-portal', sub: 'u', nonce: form.nonce, ...bad }) } }));
      await expect(OidcTokenSource.start(SETTINGS, w.env)).rejects.toThrow(SignInError);
    }
  });

  it('reports what the provider refused', async () => {
    const w = world();
    void OidcTokenSource.start(SETTINGS, w.env);
    await new Promise((r) => setTimeout(r, 10));
    w.back({ error: 'access_denied', error_description: 'The user declined.' });
    await expect(OidcTokenSource.start(SETTINGS, w.env)).rejects.toThrow('The user declined.');
  });
});

describe('renewal', () => {
  it('renews with the refresh token, and signs in again when that fails', async () => {
    const w = world();
    void OidcTokenSource.start(SETTINGS, w.env);
    await new Promise((r) => setTimeout(r, 10));
    w.back({ code: 'c-1' });
    const source = await OidcTokenSource.start(SETTINGS, w.env);
    expect(await source.refresh()).toBe(true);
    expect(w.posts[1]).toMatchObject({ grant_type: 'refresh_token', refresh_token: 'rt-1' });
    expect(source.token()).toBe('at-2');

    w.answer(() => ({ status: 400, body: { error: 'invalid_grant' } }));
    void source.refresh();
    await new Promise((r) => setTimeout(r, 10));
    expect(source.token()).toBeNull();
    expect(new URL(w.assigned!).pathname).toBe('/realms/notes/auth');
  });

  it('ends the provider session on sign-out', async () => {
    const w = world();
    void OidcTokenSource.start(SETTINGS, w.env);
    await new Promise((r) => setTimeout(r, 10));
    w.back({ code: 'c-1' });
    const source = await OidcTokenSource.start(SETTINGS, w.env);
    source.signOut();
    const to = new URL(w.assigned!);
    expect(to.pathname).toBe('/realms/notes/logout');
    expect(to.searchParams.get('post_logout_redirect_uri')).toBe('https://portal.example.com/app/');
    expect(to.searchParams.get('id_token_hint')).toBeTruthy();
    expect(source.token()).toBeNull();
  });
});

describe('the session', () => {
  const transport = (status: number, body: unknown): Transport => ({ kind: 'http', send: async () => ({ status, headers: {}, body }) });

  it('follows what the service says', async () => {
    expect(await startSession({ kind: 'simulated', send: async () => ({ status: 500, headers: {}, body: null }) })).toEqual({ kind: 'demo' });
    expect(await startSession(transport(200, { method: 'demo' }))).toEqual({ kind: 'demo' });
    expect(await startSession(transport(404, null))).toEqual({ kind: 'demo' });  // a service older than the route
    expect(await startSession(transport(200, { method: 'none' }))).toEqual({ kind: 'none' });
    const w = world();
    w.env.fetch = (async () => { throw new Error('down'); }) as typeof fetch;
    expect(await startSession(transport(200, { method: 'oidc', ...SETTINGS }), w.env)).toMatchObject({ kind: 'failed' });
  });
});

describe('the API client', () => {
  it('renews once after a 401 and sends again with the same idempotency key', async () => {
    const { ApiClient } = await import('./client');
    const sent: Record<string, string>[] = [];
    let token = 'old';
    const t: Transport = { kind: 'http', send: async (req) => {
      sent.push(req.headers ?? {});
      return req.headers?.Authorization === 'Bearer new' ? { status: 200, headers: {}, body: { ok: true } } : { status: 401, headers: {}, body: { code: 'TOKEN_EXPIRED' } };
    } };
    const api = new ApiClient(t, { token: () => token, refresh: async () => { token = 'new'; return true; } });
    expect((await api.call('POST', '/api/v1/x', { idempotencyKey: 'k-1' })).data).toEqual({ ok: true });
    expect(sent.map((h) => [h.Authorization, h['Idempotency-Key']])).toEqual([['Bearer old', 'k-1'], ['Bearer new', 'k-1']]);
  });
});
