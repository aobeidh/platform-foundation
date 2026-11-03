import type { Account, TokenSource } from './identity';

// Sign-in through an OpenID Connect provider for a portal in the browser: the Authorization Code flow with PKCE
// (RFC 7636, S256) for a public client, as OAuth 2.0 for Browser-Based Apps recommends.
//
// Tokens live in memory only. Browser storage holds just the one-time values of a sign-in under way (state, nonce,
// code verifier and the page to return to), and they are removed when the provider sends the person back. A reload
// therefore signs in again: the provider's own session usually answers at once, without asking. The ID token's
// issuer, audience, authorized party, expiry and nonce are checked; it came straight from the token endpoint over
// TLS, so its signature is not (OpenID Connect Core 3.1.3.7). The access token is renewed with the refresh token
// before it expires. When it cannot be renewed the session has ended: the source never leaves the page by itself,
// so nothing unsaved is lost, and the portal asks the person to sign in again (SessionEnded).

export interface OidcSettings { issuer: string; clientId: string; scopes: string[] }

/** What the source needs from the browser; tests pass their own. */
export interface OidcEnv {
  fetch: typeof fetch;
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
  location: { href: string; origin: string; pathname: string; search: string; hash: string; assign(url: string): void };
  replaceUrl(url: string): void;
  random(bytes: number): Uint8Array;
  sha256(data: Uint8Array): Promise<Uint8Array>;
  now(): number;
  later(fn: () => void, ms: number): unknown;
  cancel(timer: unknown): void;
}

export const browserEnv = (): OidcEnv => ({
  fetch: (...a) => fetch(...a),
  storage: sessionStorage,
  location: window.location,
  replaceUrl: (url) => window.history.replaceState(window.history.state, '', url),
  random: (n) => crypto.getRandomValues(new Uint8Array(n)),
  sha256: async (d) => new Uint8Array(await crypto.subtle.digest('SHA-256', d as BufferSource)),
  now: () => Date.now(),
  later: (fn, ms) => setTimeout(fn, ms),
  cancel: (t) => clearTimeout(t as ReturnType<typeof setTimeout>),
});

/** A sign-in that did not complete: the provider refused it, or its answer could not be trusted. */
export class SignInError extends Error {}

/** The identity provider could not be reached: trying again later may work. */
class Unreachable extends SignInError {}

const PENDING = 'pf-oidc-pending';
const EARLY_MS = 60_000;  // renew this long before the access token expires
const RETRY_MS = 30_000;  // after the provider could not be reached
const LEEWAY_S = 60;  // clock difference allowed for the ID token's expiry
// What the provider adds to the address when it sends the person back: never kept in the address bar or history.
const ANSWER = ['code', 'state', 'error', 'error_description', 'error_uri', 'iss', 'session_state'];

/** The address without what a provider's answer adds to it. */
export function withoutAnswer(href: string) {
  const u = new URL(href);
  for (const k of ANSWER) u.searchParams.delete(k);
  return `${u.pathname}${u.search}${u.hash}`;
}

export const base64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

export async function challengeOf(verifier: string, env: Pick<OidcEnv, 'sha256'>) {
  return base64url(await env.sha256(new TextEncoder().encode(verifier)));
}

function claimsOf(jwt: string): Record<string, unknown> {
  const part = jwt.split('.')[1];
  if (!part) throw new SignInError('The identity provider sent an ID token that is not a JWT.');
  const text = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='));
  return JSON.parse(decodeURIComponent(Array.from(text, (c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''))) as Record<string, unknown>;
}


interface Endpoints { issuer: string; authorization_endpoint: string; token_endpoint: string; end_session_endpoint?: string }
interface Pending { state: string; nonce: string; verifier: string; returnTo: string }
interface TokenAnswer { access_token: string; expires_in?: number; refresh_token?: string; id_token?: string }

export class OidcTokenSource implements TokenSource {
  private access: string | null = null;
  private refreshToken: string | null = null;
  private idToken: string | null = null;
  private timer: unknown = null;
  private renewing: Promise<boolean> | null = null;
  private expiresAt = 0;
  private readonly listeners = new Set<() => void>();
  ended = false;
  account: Account | null = null;

  private constructor(private readonly settings: OidcSettings, private readonly endpoints: Endpoints, private readonly env: OidcEnv) {}

  /**
   * The signed-in source. Completes a sign-in when the provider has just sent the person back; otherwise sends
   * them to the provider, and the returned promise never settles while the page leaves.
   */
  static async start(settings: OidcSettings, env: OidcEnv = browserEnv()): Promise<OidcTokenSource> {
    const endpoints = await discover(settings, env);
    const source = new OidcTokenSource(settings, endpoints, env);
    const url = new URL(env.location.href);
    const raw = env.storage.getItem(PENDING);
    const answered = url.searchParams.has('code') || url.searchParams.has('error');
    // The code is single use, but never left in the address bar or history either, whatever happens next.
    if (answered) env.replaceUrl(withoutAnswer(env.location.href));
    if (raw && answered) {
      env.storage.removeItem(PENDING);
      const pending = JSON.parse(raw) as Pending;
      env.replaceUrl(pending.returnTo);
      if (url.searchParams.get('state') !== pending.state) throw new SignInError('The sign-in answer does not belong to this sign-in.');
      const error = url.searchParams.get('error');
      if (error) throw new SignInError(url.searchParams.get('error_description') || error);
      await source.exchange({
        grant_type: 'authorization_code', code: url.searchParams.get('code') ?? '', redirect_uri: source.redirectUri(),
        client_id: settings.clientId, code_verifier: pending.verifier,
      }, pending.nonce);
      return source;
    }
    return source.signIn();
  }

  token() { return this.access; }

  subscribe(fn: () => void) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }

  /** Renews the access token with the refresh token. False when it cannot now; `ended` says whether it never will. */
  refresh(): Promise<boolean> {
    if (!this.renewing) {
      this.renewing = this.renew().finally(() => { this.renewing = null; });
    }
    return this.renewing;
  }

  /** Sends the person to the provider to sign in, and back to the page they are on. */
  async signIn(): Promise<never> {
    const verifier = base64url(this.env.random(32));
    const pending: Pending = {
      state: base64url(this.env.random(16)), nonce: base64url(this.env.random(16)), verifier,
      returnTo: withoutAnswer(this.env.location.href),
    };
    this.env.storage.setItem(PENDING, JSON.stringify(pending));
    const q = new URLSearchParams({
      response_type: 'code', client_id: this.settings.clientId, redirect_uri: this.redirectUri(),
      scope: this.settings.scopes.join(' '), state: pending.state, nonce: pending.nonce,
      code_challenge: await challengeOf(verifier, this.env), code_challenge_method: 'S256',
    });
    this.env.location.assign(`${this.endpoints.authorization_endpoint}?${q}`);
    return new Promise<never>(() => { /* the page is leaving */ });
  }

  /** Forgets the tokens and ends the provider's session, when it offers that; otherwise signs in again. */
  signOut() {
    this.ended = true;
    const hint = this.idToken;
    this.forget();
    if (this.endpoints.end_session_endpoint) {
      const q = new URLSearchParams({ client_id: this.settings.clientId, post_logout_redirect_uri: this.redirectUri(), ...(hint ? { id_token_hint: hint } : {}) });
      this.env.location.assign(`${this.endpoints.end_session_endpoint}?${q}`);
    } else {
      void this.signIn();
    }
  }

  private redirectUri() { return `${this.env.location.origin}${this.env.location.pathname}`; }

  private forget() {
    if (this.timer !== null) this.env.cancel(this.timer);
    this.timer = null;
    this.access = this.refreshToken = this.idToken = null;
  }

  private async renew(): Promise<boolean> {
    if (!this.refreshToken || this.ended) { this.end(); return false; }
    try {
      await this.exchange({ grant_type: 'refresh_token', refresh_token: this.refreshToken, client_id: this.settings.clientId });
      return true;
    } catch (e) {
      if (e instanceof Unreachable && this.env.now() < this.expiresAt) this.schedule(RETRY_MS);  // try again while it lasts
      else this.end();
      return false;
    }
  }

  /** The session cannot be renewed: the access token works until it expires, and the portal asks to sign in again. */
  private end() {
    if (this.timer !== null) this.env.cancel(this.timer);
    this.timer = null;
    this.refreshToken = null;
    if (!this.ended) { this.ended = true; this.listeners.forEach((l) => l()); }
  }

  private schedule(ms: number) {
    if (this.timer !== null) this.env.cancel(this.timer);
    this.timer = this.env.later(() => { this.timer = null; void this.refresh(); }, Math.max(5_000, ms));
  }

  private async exchange(form: Record<string, string>, nonce?: string) {
    let res: Response;
    try {
      res = await this.env.fetch(this.endpoints.token_endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
        body: new URLSearchParams(form).toString(),
      });
    } catch {
      throw new Unreachable('The identity provider could not be reached.');
    }
    if (res.status >= 500) throw new Unreachable(`The identity provider answered ${res.status}.`);
    const body = await res.json().catch(() => ({})) as TokenAnswer & { error?: string; error_description?: string };
    if (!res.ok || !body.access_token) throw new SignInError(body.error_description || body.error || `The identity provider answered ${res.status}.`);
    if (body.id_token) {
      const c = claimsOf(body.id_token);
      const aud = Array.isArray(c.aud) ? c.aud : [c.aud];
      if (c.iss !== this.settings.issuer) throw new SignInError('The ID token comes from another issuer.');
      if (!aud.includes(this.settings.clientId)) throw new SignInError('The ID token is not for this portal.');
      if (aud.length > 1 && c.azp !== this.settings.clientId) throw new SignInError('The ID token was issued to another client.');
      if (typeof c.exp !== 'number' || c.exp + LEEWAY_S < this.env.now() / 1000) throw new SignInError('The ID token has expired.');
      if (nonce !== undefined && c.nonce !== nonce) throw new SignInError('The ID token does not belong to this sign-in.');
      if (nonce === undefined && this.account && String(c.sub) !== this.account.subject) throw new SignInError('The renewed token names another person.');
      this.idToken = body.id_token;
      this.account = {
        subject: String(c.sub), name: String(c.name ?? c.preferred_username ?? c.email ?? c.sub),
        ...(typeof c.email === 'string' ? { email: c.email } : {}),
      };
    } else if (nonce !== undefined) {
      throw new SignInError('The identity provider sent no ID token. Ask for the openid scope.');
    }
    this.access = body.access_token;
    if (body.refresh_token) this.refreshToken = body.refresh_token;
    const lifetime = (body.expires_in ?? 300) * 1000;
    this.expiresAt = this.env.now() + lifetime;
    // Renewed before it expires when it can be; otherwise it lasts until it expires and the session then ends.
    if (this.refreshToken) this.schedule(lifetime - EARLY_MS);
    else { if (this.timer !== null) this.env.cancel(this.timer); this.timer = this.env.later(() => { this.timer = null; this.end(); }, lifetime); }
  }
}

async function discover(settings: OidcSettings, env: OidcEnv): Promise<Endpoints> {
  let doc: Endpoints;
  try {
    const res = await env.fetch(`${settings.issuer.replace(/\/+$/, '')}/.well-known/openid-configuration`, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(String(res.status));
    doc = await res.json() as Endpoints;
  } catch {
    throw new SignInError(`The identity provider at ${settings.issuer} could not be reached.`);
  }
  if (doc.issuer !== settings.issuer) throw new SignInError('The identity provider names another issuer than the one configured.');
  if (!doc.authorization_endpoint || !doc.token_endpoint) throw new SignInError('The identity provider does not offer the authorization code flow.');
  // Over TLS, unless the portal itself is served without it (a developer's machine).
  const secure = env.location.href.startsWith('https:');
  for (const url of [doc.issuer, doc.authorization_endpoint, doc.token_endpoint, doc.end_session_endpoint].filter(Boolean) as string[]) {
    if (secure && !url.startsWith('https:')) throw new SignInError('The identity provider must be reached over HTTPS.');
  }
  return doc;
}
