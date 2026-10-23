# ADR-0002: Hard budgets are enforced by atomic reservations in Redis

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

The product promise is that a request which would breach a hard budget never reaches the
provider. The obvious implementation, read recorded spend and call the provider if there
is room, is a race: N concurrent requests all read the same remaining balance and all
proceed. With agents and batch jobs, N is often in the dozens.

A single request can also match several budgets at once (the whole gateway, its team, its
project, its key, its end user, its model). All of them must have room, and either all
are charged or none is.

## Decision

Before the provider call, the gateway computes the request's **worst-case cost** (input
estimate at the input price plus the full output allowance at the output price) and
reserves it against every applicable budget counter in **one Lua script**. Redis runs a
script atomically, so the check and the increment cannot interleave with another request
on any instance. If any hard budget would be exceeded, nothing is charged and the request
is refused with HTTP 402.

Each counter (`ts:bud:{budget}:{window}:{scope}`) holds settled spend plus outstanding
reservations for one budget window. After the call, the reservation is replaced by the
actual cost (a signed adjustment). When a counter is missing (new window, or Redis lost
its data) the script reports it, the gateway rebuilds the value from the Postgres usage
ledger, and the reservation is retried.

If Redis cannot be reached, requests under a hard budget are refused (503), because there
is no way to prove they fit. `BUDGET_FAILURE_MODE=open` exists for deployments that value
availability over spend control, and production on AWS refuses to boot with it.

## Consequences

**Good**
- Proven, not hoped: the integration suite sends 50 concurrent requests at a budget that
  fits 10, and asserts exactly 10 reach the provider (`test_ac3_concurrent_requests_cannot_overspend`).
- One round trip for any number of budgets.
- Redis loss is survivable: counters are rebuilt from the append-only ledger.

**Bad / caveats**
- Worst-case reservation is conservative: a request near the end of a budget may be
  refused even though its real cost would have fitted. Capping `max_tokens` with a policy
  narrows the gap.
- Redis becomes part of the enforcement path. It runs with AOF and `noeviction` (see
  `infra/terraform/modules/cache`), and its failure mode is explicit.
- A process crash between reservation and settlement leaves the counter high until the
  window ends or the counter is rebuilt. That is the safe direction.

## Alternatives considered

- **Postgres row locks** (`SELECT ... FOR UPDATE` on a budget row). Correct, but it puts
  the database on every request's critical path and serialises all traffic per budget.
- **Optimistic check then reconcile.** Allows overspend by design.
- **Per-instance in-memory counters.** Wrong as soon as there are two replicas.
