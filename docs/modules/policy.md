# policy

**Purpose:** Capabilities in code, roles and separation-of-duties rules as data, evaluated behind the `PolicyEngine` port (P21).

**Use it when:** You protect an endpoint or build a menu from what a person may do.

**Do not use it when:** You need row filtering by tenant; that is tenancy and row-level security.

**Ports and API:** `PolicyEngine` (decide, capabilities).

**Providers:** `InProcessPolicyEngine`. OPA is a later provider behind the same port.

**Example:**

```python
caps.declare("connections:write", "Change connections", ar="...")
Role("integration-admin", frozenset({"connections:write"}), "tenant")
```

**Failure modes:** A role naming an undeclared capability fails the build. A person whose roles give both sides of a separation-of-duties rule gets neither.

**Telemetry:** None.
