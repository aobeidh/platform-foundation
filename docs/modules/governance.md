# governance

**Purpose:** The governed-record engine (F11): versions, lifecycle, maker-checker in code and in the database, audit, events and a generated API.

**Use it when:** Anything that changes behavior without a release: connections, rules, mappings, policies.

**Do not use it when:** Plain business data that does not need approval.

**Ports and API:** `GovernanceEngine` (create, update_draft, test, submit, approve, reject, discard, pause, resume, retire, get, list, versions, active_spec, rule_for); `GovernedKind`; `GovernedStore`; `ApprovalPolicy` with `ApprovalRule(approval, require_test)`.

**Providers:** `MemoryGovernedStore`, `PostgresGovernedStore` (row-level security; constraint `maker_checker_second_person`), `SqliteGovernedStore` (tenant scope in code; maker-checker in code and in the database, by the check `maker_checker_second_person` and by triggers that test the `edited_by` JSON array). `StaticApprovalPolicy` from settings (`APPROVAL`, `REQUIRE_TEST`) or `with_approval_policy(...)`; products may store the policy as settings of their own.

**Example:**

```python
GovernedKind(kind="connection", plural="connections", spec=ConnectionSpec, tests=(check,),
             read="connections:read", write="connections:write", approve="connections:approve")
```

**Lifecycle:** versions move draft, tested, submitted, then active (approved) or returned (with a reason). Any edit sends a pending version back to draft. `discard` drops a pending version: a record that never ran is retired; an active one keeps running. The approval rule decides what submitting means: `auto` activates at once (and still records an approved transition), `single` lets anyone with the approve capability approve, `maker_checker` needs a second person. `require_test` decides whether submitting needs a passing test. A kind may set a floor (`maker_checker="always"`) or a ceiling (`"never"`). Codes: `NOT_TESTED`, `NO_DRAFT`, `DRAFT_SUBMITTED`, `NOT_SUBMITTED`, `MAKER_CHECKER`, `NOT_ACTIVE`, `NOT_PAUSED`, `RECORD_RETIRED`, `REVISION_CONFLICT`.

**Failure modes:** Maker-checker refuses anyone who created, edited or submitted the version, in code and by the database constraint. Retired records refuse every change, and retiring withdraws any pending version. Mutations need `If-Match` with the revision. Tests run outside any transaction (P39). Products run only `active_spec`, never a draft. Overlays and promotion bundles are later milestones.

**Telemetry:** Events `<service>.<kind>.<transition>.v1`; audit stream `governed:<kind>`.
