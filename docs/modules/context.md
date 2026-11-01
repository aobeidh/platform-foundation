# context

**Purpose:** One request context (principal, tenant scope, correlation, deadline, idempotency key) propagated everywhere (F8, F10).

**Use it when:** Product code needs to know who is acting, for which tenant, or how much time is left.

**Do not use it when:** You want to set the context; only the kernel sets it (middleware, consumers, `context.use` in tests).

**Ports and API:** `RequestContext`, `Principal`, `TenantScope`; functions `current()`, `maybe_current()`, `remaining()`, `use()`.

**Providers:** None.

**Example:**

```python
ctx = context.current()
ctx.principal.subject, ctx.tenant.tenant, context.remaining()
```

**Failure modes:** `current()` outside a request raises `NoRequestContext`. Tenant-bound principals always get their own tenant, whatever they request.

**Telemetry:** Log fields `correlation_id`, `tenant`, `actor` come from the context.
