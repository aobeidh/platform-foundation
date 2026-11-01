# audit

**Purpose:** The hash-chained audit format (P17).

**Use it when:** You record a state change or verify a stream.

**Do not use it when:** You need application logs; use observability.

**Ports and API:** `AuditTrail` (append, records). The transactional variant is `uow.audit`.

**Providers:** `MemoryAuditTrail`; PostgreSQL storage is in persistence (`audit_record` table, `PostgresAuditReader`).

**Example:**

```python
uow.audit.append(AuditEntry(stream="governed:rate", action="approved", subject=id, actor=who, at=now))
```

**Failure modes:** `verify_chain` returns the first broken sequence number. Appends to one stream are serialized per transaction.

**Telemetry:** Audit actions follow `<kind>.<transition>` names; treat them as a stable API (F21).
