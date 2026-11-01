# identity

**Purpose:** Token verification behind the `TokenVerifier` port (P36).

**Use it when:** You configure how a service authenticates callers.

**Do not use it when:** You need authorization; that is the policy module.

**Ports and API:** `TokenVerifier` (verify a bearer token into a `Principal`).

**Providers:** `JwtTokenVerifier` (signed JWT with configured keys, issuer and audience); `DemoTokenVerifier` (simulated, tokens like `demo:<subject>:<roles>[:<tenant>]`, refused in production). JWKS discovery and token exchange are later providers.

**Example:**

```python
builder.with_identity(JwtTokenVerifier(key, algorithms=["RS256"], audience="svc", issuer=iss))
```

**Failure modes:** Expired tokens return `TOKEN_EXPIRED`; anything else invalid returns `TOKEN_INVALID`.

**Telemetry:** None.
