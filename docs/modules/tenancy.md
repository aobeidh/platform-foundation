# tenancy

**Purpose:** Tenant scope helpers. The same scope is applied again by row-level security in PostgreSQL (P22).

**Use it when:** You need the current tenant, must require one, or must prefix a cache or storage key.

**Do not use it when:** You want to bypass scope; platform scope comes only from platform-scoped principals or kernel jobs.

**Ports and API:** `current_scope()`, `require_tenant()`, `tenant_key()`.

**Providers:** None.

**Example:**

```python
tenant_key("rates:latest")  # 't1:rates:latest'
```

**Failure modes:** `require_tenant()` raises `PermissionError` in platform scope.

**Telemetry:** None.
