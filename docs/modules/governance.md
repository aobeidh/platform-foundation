# governance

**Purpose:** The governed-record engine (F11): versions, lifecycle, maker-checker in code and in the database, audit, events and a generated API.

**Use it when:** Anything that changes behavior without a release: connections, rules, mappings, policies.

**Do not use it when:** Plain business data that does not need approval.

**Ports and API:** `GovernanceEngine` (create, update_draft, test, submit, approve, reject, pause, resume, retire, get, list, versions, active_spec); `GovernedKind`; `GovernedStore`.

**Providers:** `MemoryGovernedStore`, `PostgresGovernedStore` (row-level security; constraint `maker_checker_second_person`).

**Example:**

```python
GovernedKind(kind="connection", plural="connections", spec=ConnectionSpec, tests=(check,),
             read="connections:read", write="connections:write", approve="connections:approve")
```

**Failure modes:** Maker-checker refuses anyone who created, edited or submitted the version, in code and by the database constraint. Retired records refuse every change, and retiring withdraws any pending version. Mutations need `If-Match` with the revision. Tests run outside any transaction (P39). Products run only `active_spec`, never a draft. Overlays and promotion bundles are later milestones.

**Telemetry:** Events `<service>.<kind>.<transition>.v1`; audit stream `governed:<kind>`.
