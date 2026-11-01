// The token source port. Demo identities are a simulated provider (labelled in the UI, refused in production by
// the kernel); an OIDC provider would return the signed-in user's access token instead.

export interface TokenSource { token(): string | null }

export interface DemoIdentity { id: string; subject: string; displayName: string; roles: string[]; tenant: string | null; roleKey: string }

export const demoToken = (d: DemoIdentity) => `demo:${d.subject}:${d.roles.join(',')}:${d.tenant ?? ''}`;

export class DemoTokenSource implements TokenSource {
  constructor(private current: DemoIdentity) {}
  set(identity: DemoIdentity) { this.current = identity; }
  get identity() { return this.current; }
  token() { return demoToken(this.current); }
}
