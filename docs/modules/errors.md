# errors

**Purpose:** The error catalog (P51): status, retryable flag, title and remedy for every code.

**Use it when:** You add an error a client may see; add it to your product's `errors.yaml`.

**Do not use it when:** You need a free-text error; clients must decide from codes, never from text.

**Ports and API:** `ErrorCatalog` (from_yaml, merge, problem).

**Providers:** `kernel_catalog()` holds kernel codes such as `VALIDATION_FAILED`, `REVISION_CONFLICT`, `MAKER_CHECKER`, `NOT_TESTED`, `PLUGIN_FAILED`, `DEADLINE_EXCEEDED`.

**Example:**

```yaml
CONNECTION_NOT_ACTIVE: {status: 409, retryable: false, title: Connection not active, remedy: Approve it first.}
```

**Failure modes:** Unknown codes map to `INTERNAL_ERROR`. Defining one code twice with different content fails at start.

**Telemetry:** None.
