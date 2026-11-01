# ADR 0003: Identity through OIDC, and calls between services through token exchange

Status: accepted
Date: 2026-11-01   Principles: P36, P23, P26, F23

## Context

Milestone 0.1 verified tokens with configured keys or demo tokens. Real deployments use an identity provider
(Keycloak locally, the client's provider in production) whose signing keys rotate, and services must call each other
either as themselves or on behalf of the user who started the request.

## Decision

- `OidcTokenVerifier` accepts only asymmetric algorithms and reads keys from a `JwksSource`. `CachedJwksSource`
  refreshes when keys are stale or a token names an unknown key id, at most once every 30 seconds, so unknown ids
  cannot be used to flood the identity provider.
- The JWKS endpoint and the token endpoint are reached through the egress policy and the resilient client like any
  other outbound call. The builder refuses to start if the JWKS host is not on the allowlist.
- `OAuthTokenService` provides client-credentials tokens (`ServiceTokens`) and RFC 8693 token exchange
  (`TokenExchanger`), cached until shortly before expiry. The cache key holds a hash of the subject token, never the
  token itself.
- The middleware keeps the caller's bearer token in the request context (excluded from `repr`, never logged).
  `platform.service_client(..., acting="caller")` exchanges it for the target audience and fails closed with
  `FORBIDDEN` when there is no caller token (background work, public routes). `acting="service"` uses the
  service's own token; the choice is always explicit, never a silent fallback.
- A token without a tenant claim is refused unless it carries a configured platform role (`platform_roles`).
- A failed JWKS refresh keeps the last good keys and backs off; with no keys, verification answers
  `DEPENDENCY_UNAVAILABLE`. Verification runs in a worker thread so a slow identity provider never blocks the loop.

## Alternatives considered

- **Forward the caller's token unchanged.** Simple, but the downstream service would accept a token issued for
  another audience, and audit could not tell the acting service from the user.
- **Always call as the service.** Loses the user's identity and tenant downstream, so row-level security and audit
  there would see only the service.

## Consequences

- OpenID discovery (`.well-known/openid-configuration`) is not used yet; the JWKS URL is configured explicitly.
- Token exchange needs the identity provider to allow it for the calling client (Keycloak: token exchange feature).
