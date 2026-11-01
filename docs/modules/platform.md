# platform

**Purpose:** The `Platform` builder: the only way to assemble the kernel (F6).

**Use it when:** Every product's `wiring.py` and every embedding host.

**Do not use it when:** Never instantiate kernel providers by hand in product code.

**Ports and API:** `Platform.builder(service, settings)` with `with_identity`, `with_capabilities`, `with_roles`, `with_governed_kinds`, `with_plugin_kind`, `with_provider`, `with_migrations`, `with_secrets`, `with_egress`, `with_errors`; then `build()`, `create_app()`, `migrate()`.

**Providers:** Chooses persistence by `PROVIDER_PERSISTENCE` (default postgres when `DATABASE_URL` is set, otherwise memory).

**Example:**

```python
platform = Platform.builder("connections", settings).with_capabilities(declare).with_roles(ROLES).build()
```

**Failure modes:** Every configuration problem is listed in one `ConfigurationError`. Simulated providers and `ALLOW_DEMO` are refused when `ENVIRONMENT=production` (F23).

**Telemetry:** None.
