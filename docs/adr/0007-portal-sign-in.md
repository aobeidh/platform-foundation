# ADR 0007: Portal sign-in through OIDC, decided by the service

## Status

Accepted (milestone 0.4).

## Context

The kernel has verified OIDC bearer tokens since 0.1 (ADR 0003), but the portal kit only had demo identities, so a
product could not be run with real people. The Integration Hub, the second product on the foundation, now needs a
deployment where people sign in with their organization's identity provider. Every product's portal needs the same
thing, so it belongs in the foundation (F2).

A portal must learn how to sign people in before anyone is signed in, and the service already holds the provider's
settings. Some services run inside the cluster next to their identity provider, and must fetch its keys from a
private address, sometimes without TLS in development.

## Decision

- **The service says how to sign in.** `GET /api/v1/portal/sign-in` is public. It answers
  `{"method": "oidc", "issuer", "clientId", "scopes"}` when `with_oidc` names a `portal_client_id`, `{"method": "demo"}`
  with demo tokens, and `{"method": "none"}` otherwise, for services whose tokens come from a host application. It
  holds nothing secret: the client is public and the issuer publishes the rest. In production the issuer must use
  https when a portal client is set.
- **The browser uses the Authorization Code flow with PKCE (S256)**, as a public client, as OAuth 2.0 for
  Browser-Based Apps recommends. `OidcTokenSource` implements the `TokenSource` port. It discovers the provider and
  checks that it names exactly the configured issuer, with https endpoints whenever the portal itself uses https. It
  checks the `state`, and the ID token's issuer, audience, authorized party, expiry and nonce, and on renewal that it
  names the same person. The ID token comes straight from the token endpoint over TLS, so its signature is not
  checked (OpenID Connect Core 3.1.3.7). Whatever the provider adds to the address when it sends the person back
  (the code, the state, an error) is removed at once, also when no sign-in was waiting for it.
- **Tokens stay in memory.** Browser storage holds only the one-time values of a sign-in under way, which are removed
  when the provider answers, so script injected into the page finds no stored tokens. A reload signs in again; the
  provider's own session usually answers without asking. The access token is renewed with the refresh token a minute
  before it expires, and again after 30 seconds while the provider cannot be reached.
- **The source never leaves the page by itself.** When the session cannot be renewed (no refresh token, or the
  provider refuses it) it has ended: the access token works until it expires, and `SessionEnded` asks the person to
  sign in again when they choose, so nothing unsaved is lost and a token the service keeps refusing cannot cause a
  loop of redirects.
- **The API client renews once, and only an expired token.** A call refused with `TOKEN_EXPIRED` renews the token and
  is sent again. The kernel refuses it in its authentication step, before the call runs, so nothing is applied twice.
  A token renewed while the call was under way is used at once. Other refusals (another audience, a missing tenant)
  are not renewed: a new token would be refused the same way.
- **`startSession(transport)` chooses the session once at start-up.** The simulated transport means demo identities;
  a service that does not answer the route (a proxy in front of it, another mount) is a failed sign-in, never demo. `ApiProvider` takes either demo identities or a signed-in token source with its
  `account`. `AccountMenu` shows the signed-in person and signs them out (ending the provider's session when it
  offers that), and `SignInProblem` replaces the portal when sign-in cannot complete.
- **Egress for internal providers.** `EGRESS_ALLOW_PRIVATE` and `EGRESS_ALLOW_PLAIN_HTTP` list allowed hosts that
  may resolve privately or be reached without TLS. Plain HTTP is refused when `ENVIRONMENT=production`.

## Consequences

- A product turns on real sign-in with configuration: `with_oidc(..., portal_client_id=...)` and a public client in
  its identity provider whose redirect URI is the portal's address.
- The identity provider must allow the portal's origin for cross-origin calls to its discovery and token endpoints,
  or be served from the portal's origin behind the same proxy.
- `useApi().identity` is now `null` when people sign in through a provider. Code that reads it must allow for that.
- A reload costs a round trip to the identity provider.
