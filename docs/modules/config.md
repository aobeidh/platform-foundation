# config

**Purpose:** Settings, provider selection and secret references.

**Use it when:** A service reads its configuration or chooses a provider with `PROVIDER_<PORT>`.

**Do not use it when:** You want to read environment variables in product code; read `PlatformSettings` instead.

**Ports and API:** `SecretStore` (resolve a reference such as `env://NAME`).

**Providers:** `EnvSecretStore` (production), `MemorySecretStore` (simulated). Keys: `ENVIRONMENT`, `DATABASE_URL`, `DATABASE_SCHEMA`, `REQUEST_TIMEOUT_SECONDS`, `MAX_BODY_BYTES`, `IDEMPOTENCY_RETENTION_HOURS`, `ALLOW_DEMO`, `EGRESS_ALLOWLIST`, `PROVIDER_*`.

**Example:**

```python
settings = PlatformSettings.from_env("connections")
settings.provider("activations", "memory")
```

**Failure modes:** An unknown provider name fails the build with the list of valid names. Secrets are never logged.

**Telemetry:** None.
