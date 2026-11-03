import { OidcTokenSource, SignInError, browserEnv, type OidcEnv, type OidcSettings } from './oidc';
import type { Transport } from './transport';

// How a portal signs people in, decided once at start-up from the service's answer to GET /api/v1/portal/sign-in
// (the kernel's public route): an OIDC provider, the demo identities of a development service or the simulated
// provider, or nothing the portal can use.

export type SignIn = { method: 'oidc'; issuer: string; clientId: string; scopes: string[] } | { method: 'demo' } | { method: 'none' };

export type Session =
  | { kind: 'demo' }
  | { kind: 'oidc'; tokens: OidcTokenSource }
  | { kind: 'none' }
  | { kind: 'failed'; reason: string };

/**
 * The session for this portal. With OIDC it completes or starts a sign-in; while the browser goes to the identity
 * provider, the promise does not settle.
 */
export async function startSession(transport: Transport, env?: OidcEnv): Promise<Session> {
  if (transport.kind === 'simulated') return { kind: 'demo' };
  const res = await transport.send({ method: 'GET', path: '/api/v1/portal/sign-in', headers: {} });
  // Never demo by default: a service that does not answer (a proxy in front of it, another mount) is a failure.
  if (res.status !== 200) return { kind: 'failed', reason: `The service answered ${res.status} when asked how to sign in.` };
  const how = res.body as SignIn;
  if (how.method === 'demo') return { kind: 'demo' };
  if (how.method !== 'oidc') return { kind: 'none' };
  try {
    const settings: OidcSettings = { issuer: how.issuer, clientId: how.clientId, scopes: how.scopes };
    return { kind: 'oidc', tokens: await OidcTokenSource.start(settings, env ?? browserEnv()) };
  } catch (e) {
    return { kind: 'failed', reason: e instanceof SignInError ? e.message : 'The sign-in could not be completed.' };
  }
}
