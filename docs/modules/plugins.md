# plugins

**Purpose:** One plugin host for every plugin kind (F12): SPI version check, descriptor and config validation, publisher check, timeouts and error translation.

**Use it when:** A product lets users choose among implementations at run time (connectors, steps, channels).

**Do not use it when:** Only one implementation runs per deployment; that is a provider, not a plugin.

**Ports and API:** `PluginHost` (register, discover, get, descriptors, validate_config, call); `SignatureVerifier`.

**Providers:** `PublisherAllowlistVerifier` (interim), `AllowUnsignedVerifier` (simulated, refused in production). Sigstore verification and out-of-process isolation are later.

**Example:**

```python
builder.with_plugin_kind("connector", ConnectorSpi, "0.1.0", discover_group="exemplar.connectors")
```

**Failure modes:** A plugin that fails to load is logged and refused; the host keeps running. Calls past the timeout return `PLUGIN_FAILED`. Calls run with a copy of the request context, so deadline, tenant and correlation reach the plugin; all plugins share one egress-bound client, breaker and bulkhead from `platform.plugin_context()`.

**Telemetry:** Metric `plugin.call.duration{plugin,kind}`.
