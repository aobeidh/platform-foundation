# identity

**Purpose:** Token verification behind the `TokenVerifier` port (P36).

**Use it when:** You configure how a service authenticates callers.

**Do not use it when:** You need authorization; that is the policy module.

**Ports and API:** `TokenVerifier` (verify a bearer token into a `Principal`), `JwksSource`, `TokenExchanger` (RFC 8693), `ServiceTokens` (client credentials).

**Providers:** `JwtTokenVerifier` (signed JWT with configured keys, issuer and audience); `OidcTokenVerifier` (asymmetric algorithms only; keys from `CachedJwksSource`, refreshed on an unknown key id at most every 30 seconds; Keycloak `realm_access` roles understood; `act` claim becomes `on_behalf_of`), `StaticJwksSource`, `JwtTokenVerifier`, `DemoTokenVerifier` (simulated, refused in production). The token ports are implemented by `OAuthTokenService` in the http module.

**Example:**

```python
builder.with_oidc(issuer=ISS, audience="connections", jwks_url=f"{ISS}/protocol/openid-connect/certs")
```

**Failure modes:** Expired tokens return `TOKEN_EXPIRED`; anything else invalid returns `TOKEN_INVALID`. A token without a tenant claim is refused unless it carries one of the configured `platform_roles`, so a missing claim never widens access to platform scope. When the identity provider cannot be reached, the last good keys stay in use and refreshes back off; with no keys at all, verification returns `DEPENDENCY_UNAVAILABLE` (503). Verification runs off the event loop.

**Telemetry:** None.
