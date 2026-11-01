# observability

**Purpose:** Structured JSON logs with context fields and redaction, tracing and metrics through OpenTelemetry (P27, I19).

**Use it when:** Always: every service calls `configure_logging` at start.

**Do not use it when:** You want to log secrets or personal data; the redaction filter removes known secret keys, but do not rely on it.

**Ports and API:** `configure_logging`, `get_logger`, `tracer`, `meter`, `redact`.

**Providers:** OpenTelemetry API only; install and configure an SDK and exporter in deployment.

**Example:**

```python
log = get_logger("svc")
log.info("thing.created", thing_id=tid)
```

**Failure modes:** Without an OpenTelemetry SDK, spans and metrics are no-ops.

**Telemetry:** Metrics: `http.server.requests`, `http.server.duration`, `http.client.duration`, `plugin.call.duration`. Log fields: `service`, `version`, `environment`, `correlation_id`, `tenant`, `actor`, `trace_id`, `span_id`.
