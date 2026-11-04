# platform

**Purpose:** The `Platform` builder: the only way to assemble the kernel (F6).

**Use it when:** Every product's `wiring.py` and every embedding host.

**Do not use it when:** Never instantiate kernel providers by hand in product code.

**Ports and API:** `Platform.builder(service, settings)` with `with_identity`, `with_capabilities`, `with_roles`, `with_governed_kinds`, `with_plugin_kind`, `with_provider`, `with_migrations`, `with_secrets`, `with_egress`, `with_errors`, `with_expressions`, `with_oidc`, `with_oauth`; then `build()`, `create_app()`, `migrate()`, `service_client()` (acts for the caller through token exchange and refuses without a caller token, or as the service; `with_oidc(platform_roles=...)` names the staff roles allowed without a tenant claim), `expressions`, `operations`, `capabilities`. Every app also serves the portal API under `/api/v1/portal` (`me`, `kinds`, `plugins`) that `@platform/web-kit` reads (ADR 0005).

**Providers:** Chooses persistence by `PROVIDER_PERSISTENCE` (`memory`, `postgres` or `sqlite`). Without it, `default_persistence(DATABASE_URL)` decides: sqlite when the URL's SQLAlchemy backend is `sqlite` (`sqlite:///x.db`, `sqlite+pysqlite:///x.db`), postgres for any other `DATABASE_URL`, otherwise memory. The postgres provider refuses a backend other than `postgresql`. Products can use the same function for the defaults of their own ports.

**Example:**

```python
platform = Platform.builder("connections", settings).with_capabilities(declare).with_roles(ROLES).build()
```

**Failure modes:** Every configuration problem is listed in one `ConfigurationError`. Simulated providers and `ALLOW_DEMO` are refused when `ENVIRONMENT=production` (F23).

**Telemetry:** None.
