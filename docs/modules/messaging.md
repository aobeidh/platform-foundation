# messaging

**Purpose:** The outbox relay, transports and the consumer runtime with inbox, retries and dead letters (P18, P19, I7).

**Use it when:** You react to an event, inside or across services.

**Do not use it when:** You need a synchronous answer; call the owning service instead.

**Ports and API:** `Transport`; `ConsumerRuntime.subscribe(type, consumer, handler, retry)`; `PollingRelay.run_once()`; `make_event`.

**Providers:** `LocalTransport` (in-process). Broker transports (Kafka, AMQP) are later providers behind `Transport`.

**Example:**

```python
platform.consumers.subscribe("svc.thing.approved.v1", "record", handler)
platform.relay.run_once()
```

**Failure modes:** `InvalidMessage` goes to the invalid channel without retry; other errors retry up to the policy, then dead-letter; expired envelopes dead-letter with `EXPIRED`. The relay stops at the first failure to keep order.

**Telemetry:** None yet.
