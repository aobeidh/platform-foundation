# contracts

**Purpose:** Wire formats shared by every product: RFC 9457 problem details, the CloudEvents envelope with integration headers, and pages.

**Use it when:** You build an HTTP error body, publish an event, or return a list.

**Do not use it when:** You need product-specific payloads; put those in the product's contract.

**Ports and API:** Models: `Problem`, `Envelope`, `HistoryEntry`, `Page`.

**Providers:** None. The JSON Schemas in `spec/` are generated from these models and checked by `pk check spec`.

**Example:**

```python
Envelope(id=new_id(), source="svc", type="svc.thing.created.v1", time=now, correlationid=cid)
```

**Failure modes:** Event types must be dotted and end with a version (`.v1`). Timestamps must be timezone aware.

**Telemetry:** None.
