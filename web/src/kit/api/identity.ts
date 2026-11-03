// The token source port. Demo identities are a simulated provider (labelled in the UI, refused in production by
// the kernel); OidcTokenSource (./oidc) returns the signed-in person's access token instead.

export interface TokenSource {
  token(): string | null;
  /** Renews the token after the service refused it as expired; false when it cannot. Never leaves the page. */
  refresh?(): Promise<boolean>;
  /** True once the session cannot be renewed: the person must sign in again. */
  readonly ended?: boolean;
  /** Calls `fn` when `ended` changes; returns the unsubscribe function. */
  subscribe?(fn: () => void): () => void;
  /** Sends the person to sign in again, back to the page they are on. */
  signIn?(): void;
}

/** The person signed in through an identity provider, as the portal shows them. */
export interface Account { subject: string; name: string; email?: string }

export interface DemoIdentity { id: string; subject: string; displayName: string; roles: string[]; tenant: string | null; roleKey: string }

export const demoToken = (d: DemoIdentity) => `demo:${d.subject}:${d.roles.join(',')}:${d.tenant ?? ''}`;

export class DemoTokenSource implements TokenSource {
  constructor(private current: DemoIdentity) {}
  set(identity: DemoIdentity) { this.current = identity; }
  get identity() { return this.current; }
  token() { return demoToken(this.current); }
}
