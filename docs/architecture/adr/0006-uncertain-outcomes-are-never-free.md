# ADR-0006: A request whose outcome is unknown is never recorded as free

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

When a provider call times out after the request was sent, or a streaming client
disconnects mid-answer, the gateway does not know what the provider billed. Providers
generally keep generating and charge for it. Recording such a request at zero cost would
let a misbehaving client drain a budget invisibly: time out every call, pay nothing on
paper.

The adapters can tell the difference between "never sent" (connection refused, connect
timeout: nothing can have been billed) and "sent, no answer" (read timeout, connection
reset, client disconnect).

## Decision

- **Not sent:** release the reservation and record an `ERROR` event.
- **Sent, no answer:** record an `UNCERTAIN` event with zero actual cost, and keep the
  budget reservation outstanding (the counter keeps the worst case).
- After `UNCERTAIN_SETTLE_AFTER_S` (15 minutes by default) the worker settles the request
  at its reserved worst case: a reconciliation event adds that amount to recorded spend,
  and the reservation rows are marked settled.

## Consequences

**Good**
- Budgets cannot be bypassed by timing out, and analytics include the held amount.
- The append-only ledger stays append-only: corrections are new reconciliation events.

**Bad / caveats**
- Conservative: an uncertain request is charged its worst case even if the provider
  billed less. The provider APIs used here offer no per-request usage lookup to do better.
  A provider-specific reconciler could replace the default settlement later.

## Alternatives considered

- **Assume zero.** Rejected: a budget bypass.
- **Retry the call.** Rejected: can double bill, and the original may still complete.
