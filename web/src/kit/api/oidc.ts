import type { Account, TokenSource } from './identity';

// Sign-in through an OpenID Connect provider for a portal in the browser: the Authorization Code flow with PKCE
// (RFC 7636, S256) for a public client, as OAuth 2.0 for Browser-Based Apps recommends.
//
// Tokens live in memory only. Browser storage holds just the one-time values of a sign-in under way (state, nonce,
// code verifier and the page to return to), and they are removed when the provider sends the person back. A reload
// therefore signs in again: the provider's own session usually answers at once, without asking. The ID token's
// nonce, issuer and audience are checked; it came straight from the token endpoint over TLS, so its signature is not
// (OpenID Connect Core 3.1.3.7). The access token is renewed with the refresh token before it expires; when that is
// not possible, the person goes through sign-in again and comes back to the page they were on.

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

const PENDING = 'pf-oidc-pending';
const EARLY_MS = 60_000;  // renew this long before the access token expires

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

const trim = (url: string) => url.replace(/\/+$/, '');

interface Endpoints { issuer: string; authorization_endpoint: string; token_endpoint: string; end_session_endpoint?: string }
interface Pending { state: string; nonce: string; verifier: string; returnTo: string }
interface TokenAnswer { access_token: string; expires_in?: number; refresh_token?: string; id_token?: string }

export class OidcTokenSource implements TokenSource {
  private access: string | null = null;
  private refreshToken: string | null = null;
  private idToken: string | null = null;
  private timer: unknown = null;
  private renewing: Promise<boolean> | null = null;
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
    if (raw && (url.searchParams.has('code') || url.searchParams.has('error'))) {
      env.storage.removeItem(PENDING);
      const pending = JSON.parse(raw) as Pending;
      env.replaceUrl(pending.returnTo);  // the code is single use: never leave it in the address bar or history
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

  /** Renews the access token with the refresh token; without one, or when renewal fails, signs in again. */
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
      returnTo: `${this.env.location.pathname}${this.env.location.search}${this.env.location.hash}`,
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
    if (this.refreshToken) {
      try {
        await this.exchange({ grant_type: 'refresh_token', refresh_token: this.refreshToken, client_id: this.settings.clientId });
        return true;
      } catch { /* the provider's session ended: sign in again */ }
    }
    this.forget();
    return this.signIn();
  }

  private async exchange(form: Record<string, string>, nonce?: string) {
    let res: Response;
    try {
      res = await this.env.fetch(this.endpoints.token_endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
        body: new URLSearchParams(form).toString(),
      });
    } catch {
      throw new SignInError('The identity provider could not be reached.');
    }
    const body = await res.json().catch(() => ({})) as TokenAnswer & { error?: string; error_description?: string };
    if (!res.ok || !body.access_token) throw new SignInError(body.error_description || body.error || `The identity provider answered ${res.status}.`);
    if (body.id_token) {
      const c = claimsOf(body.id_token);
      const aud = Array.isArray(c.aud) ? c.aud : [c.aud];
      if (trim(String(c.iss)) !== trim(this.settings.issuer)) throw new SignInError('The ID token comes from another issuer.');
      if (!aud.includes(this.settings.clientId)) throw new SignInError('The ID token is not for this portal.');
      if (nonce !== undefined && c.nonce !== nonce) throw new SignInError('The ID token does not belong to this sign-in.');
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
    if (this.timer !== null) this.env.cancel(this.timer);
    const lifetime = (body.expires_in ?? 300) * 1000;
    this.timer = this.env.later(() => { void this.refresh(); }, Math.max(5_000, lifetime - EARLY_MS));
  }
}

async function discover(settings: OidcSettings, env: OidcEnv): Promise<Endpoints> {
  let doc: Endpoints;
  try {
    const res = await env.fetch(`${trim(settings.issuer)}/.well-known/openid-configuration`, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(String(res.status));
    doc = await res.json() as Endpoints;
  } catch {
    throw new SignInError(`The identity provider at ${settings.issuer} could not be reached.`);
  }
  if (trim(doc.issuer ?? '') !== trim(settings.issuer)) throw new SignInError('The identity provider names another issuer than the one configured.');
  if (!doc.authorization_endpoint || !doc.token_endpoint) throw new SignInError('The identity provider does not offer the authorization code flow.');
  return doc;
}
