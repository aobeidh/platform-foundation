# operations

**Purpose:** Long-running work as a resource (202, status, cancel) and sagas on an in-process orchestrator (P39, I12).

**Use it when:** Work may take longer than a request budget, or spans several steps that must be undone together on failure.

**Do not use it when:** The work finishes well within the request deadline; answer directly.

**Ports and API:** `OperationRunner` (register, register_saga, start, get, recent, cancel, resume_unfinished; `GET /operations` lists what the caller may see), `Handle` (progress, save_state, check_cancelled), `Saga`, `SagaStep`, `SagaStalled`, `accepted()`, `operations_router`, `Orchestrator` port. Statuses: pending, running, stalled, succeeded, failed, cancelled.

**Providers:** In-process runner with `MemoryOperationStore`, `PostgresOperationStore` (table `operation`, row-level security) or `SqliteOperationStore` (tenant scope in code; the unit of work's write lock replaces row locks). Temporal is a later provider behind `Orchestrator`.

**Example:**

```python
platform.operations.register("report", build_report)
return accepted(platform.operations.start("report", body))  # 202 + Location
```

**Failure modes:** Work runs with the creator's subject, roles and tenant, the same correlation id and its own deadline (default one hour). It has no caller token, so `service_client(acting="caller")` refuses inside it; use `acting="service"`. Every change takes a row lock, so a cancel is never lost to a progress update and does nothing once the operation finished. A runner claims an operation with a lease as long as the deadline; `resume_unfinished()` skips work running here or leased by another live instance, so nothing runs twice at once. Past the deadline, `check_cancelled()` raises and the operation fails with `DEADLINE_EXCEEDED`; status changes still land. Saga state is saved after every step, so actions and compensations must be idempotent. A failing compensation makes the operation `stalled`, which `resume_unfinished()` picks up again. Unexpected errors are logged; the operation shows only `INTERNAL_ERROR` with a generic detail. Only the creator, holders of `operations.read` in the same tenant, or platform staff can see an operation; only the creator or staff may cancel. Cancellation is cooperative.

**Telemetry:** Events `<service>.operation.accepted|cancel_requested|succeeded|failed|stalled|cancelled.v1`; logs `operation.failed`, `operation.stalled`, `saga.step_failed`.
