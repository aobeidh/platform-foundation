# http

**Purpose:** The app factory with the fixed middleware stack (F7), authorization, and the resilient outbound client with the egress policy (P23, P26).

**Use it when:** Every service exposes HTTP through `platform.create_app`; every outbound call uses `platform.http_client`.

**Do not use it when:** You want to add your own authentication or error format; the stack is fixed on purpose.

**Ports and API:** `create_app`, `Authorizer.require(capability)`, `DomainException`, `ResilientClient`, `EgressPolicy`, `OAuthTokenService` (client credentials and RFC 8693 token exchange, cached until shortly before expiry, never keyed by the raw token).

**Providers:** Stack order: correlation id, tracing, deadline (`Request-Deadline` header, capped by settings), body limit, authentication, tenant scope, idempotency (`Idempotency-Key` on unsafe methods), problem details, metrics. Simulated providers are listed in `X-Platform-Simulated`.

**Example:**

```python
client = platform.http_client("catalogue", "https://catalogue.internal")
client.request("GET", "/api/v1/skus")
```

**Failure modes:** Public paths match exactly. Idempotency keys are scoped to the caller and hash the method, path, query and body; replays return the stored status, body, ETag and Location. A 504 keeps the key reserved until its lease ends, because the outcome is unknown. Python cannot cancel threads, so when the deadline passes the middleware answers 504 itself and drops whatever the abandoned work sends; the work stops at its next kernel boundary (opening a unit of work, an outbound call, or the PostgreSQL statement timeout). Outbound calls connect to the address that passed the egress check (TLS verified against the host name), reject non-global addresses, bound the whole call by the budget, retry only idempotent requests, and use a breaker that lets one trial through when half-open.

**Telemetry:** Metrics `http.server.requests`, `http.server.duration`, `http.client.duration`.
