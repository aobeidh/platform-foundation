# core

**Purpose:** Pure building blocks every other module uses: Result, DomainError, UUIDv7 identifiers and the Clock.

**Use it when:** You return business outcomes from a use case, create identifiers, or need the current time.

**Do not use it when:** You need I/O of any kind; core imports nothing outside the standard library and the plugin SDK.

**Ports and API:** `Clock` (now). Types: `Ok`, `Err`, `Result`, `DomainError`, `ConcurrencyConflict`, `NotFound`.

**Providers:** `SystemClock`; `FixedClock` for tests. `uuid7()` and `new_id()` generate time-ordered RFC 9562 version 7 identifiers.

**Example:**

```python
from platform_kernel.core import Err, Ok, DomainError
return Err(DomainError("NOT_TESTED", "Run the test first."))
```

**Failure modes:** A naive datetime passed to `FixedClock` raises `ValueError`. IDs are monotonic within a process, not across processes.

**Telemetry:** None.
