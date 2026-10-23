# ADR-0004: Usage events go through a Redis Stream, drained to Postgres by workers

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

Every request produces a usage event and, when budgets apply, ledger rows. The first
implementation wrote them synchronously to Postgres before answering. Profiling the hot
path on a laptop (Docker Desktop, Redis round trip about 0.37 ms) showed that this single
insert cost about **10.6 ms at p50**, roughly half of a 24 ms cache-miss request. A gateway
that adds tens of milliseconds to every call is a gateway people route around.

## Decision

The gateway appends each record to a Redis Stream (`ts:usage:stream`) with `XADD`, in the
same pipeline as the budget settlement, cache store and coalescing-lock release, so the
whole settlement is **one round trip**. Workers read the stream through a consumer group,
insert batches of up to 500 records in one transaction, and acknowledge entries only after
the commit. Entries left pending by a crashed worker are reclaimed (`XAUTOCLAIM`) by
another. Inserts ignore duplicate `request_id`s, so at-least-once delivery never double
counts. If Redis rejects the `XADD`, the record is written directly to Postgres instead.

## Consequences

**Good**
- Measured in-process on the same laptop, the full cache-miss path dropped from about
  24.1 ms to 3.6 ms at p50; settlement from 11.9 ms to 0.6 ms.
- Postgres sees batched writes, which scale far better than one transaction per request.
- Any number of workers can drain in parallel.

**Bad / caveats**
- The dashboard is eventually consistent with the gateway. With a worker running, the lag
  is milliseconds; without one, events accumulate in Redis (the stream is capped at about
  a million entries).
- If Redis loses data before a worker drains it, up to about a second of usage events can
  be lost (AOF `everysec`). Budget counters are rebuilt from Postgres in that case, so the
  loss shows as slightly lower recorded spend, never as a budget bypass during normal
  operation.

## Alternatives considered

- **Synchronous Postgres insert.** Correct and simple; rejected on measured latency.
- **In-process batching.** Fast, but a crashed API process loses its buffer.
- **SQS or Kafka.** Adds a moving part to every deployment; Redis is already required.
