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

**Public routes:** `create_app(public_routers=...)` (or `Platform.create_app(public_routers=...)`) takes routers whose routes authenticate their callers themselves, such as a webhook receiver that checks a signature. A request skips token authentication only when the route the router will run is one of them: the middleware asks the app's routes in order, so a protected route that matches the path first keeps its authentication, and a mount or a root path cannot make another route public. Each public route starts with a fixed segment outside `/api`, `/health` and the docs, and a public router holds only its own API routes. The routes are taken as they are when the app is created: a route added to a public router later is not public. A public route runs as `context.ANONYMOUS`, whose tenant scope matches no tenant and is never platform scope; once it has authenticated its caller, it acts as a partner in exactly one tenant:

```python
with context.as_partner(f"webhook:{name}", tenant):
    ...  # the subject is "\u2205partner:webhook:<name>", kind "partner"
```

No token can name the anonymous caller or a partner: the middleware refuses a token whose principal has kind `anonymous` or `partner`, or a subject or tenant that starts with `\u2205`. The deadline, body limit, correlation id, tracing, problem details and metrics still apply; idempotency does not, because every anonymous caller would share one key space. An operation a partner starts belongs to that partner, so its `Location` is not readable by the sender; answer a webhook with what the sender needs instead.

**Failure modes:** The kernel's own public paths match exactly. The stack authenticates HTTP requests only, so it closes websocket connections (code 1008) rather than let one reach a handler without a principal. Idempotency keys are scoped to the caller and hash the method, path, query and body; replays return the stored status, body, ETag and Location. A 504 keeps the key reserved until its lease ends, because the outcome is unknown. Python cannot cancel threads, so when the deadline passes the middleware answers 504 itself and drops whatever the abandoned work sends; the work stops at its next kernel boundary (opening a unit of work, an outbound call, or the PostgreSQL statement timeout). Outbound calls connect to the address that passed the egress check (TLS verified against the host name), reject non-global addresses, bound the whole call by the budget, retry only idempotent requests, and use a breaker that lets one trial through when half-open.

**Telemetry:** Metrics `http.server.requests`, `http.server.duration`, `http.client.duration`.
