# Budget enforcement

A TokenShield budget is a promise: under a **hard** budget, a request that would exceed
the limit never reaches the provider. This document explains how that promise is kept
under concurrency, across replicas, and when things fail. The decision record is
[ADR-0002](adr/0002-atomic-budget-reservations-in-redis.md).

## Scopes and periods

| Scope | Matches a request when | Counter key suffix |
| --- | --- | --- |
| `global` | always | `all` |
| `team` | the key's project belongs to that team | team id |
| `project` | the key belongs to that project | project id |
| `api_key` | the request used that key | key id |
| `end_user` | the request carries `x-tokenshield-user` (or the OpenAI `user` field) equal to `scope_id`; `*` gives each user their own counter | the user id |
| `model` | the request asks for that alias | the alias |

Periods are UTC calendar windows: `daily` (from 00:00), `weekly` (from Monday 00:00),
`monthly` (from the 1st) and `total` (never resets). Counter keys embed the window start,
`ts:bud:{budget_id}:{YYYYMMDD}:{scope}`, and expire a day after the window ends.

Modes: **hard** budgets block; **soft** budgets never block but raise an alert when they
cross their threshold or the limit. Both are charged, so the dashboard shows real spend
against either.

## What is reserved

```
worst_case = input_estimate x input_price + output_allowance x output_price
```

The input estimate comes from tiktoken (or characters / 4 for other tokenizers). The
output allowance is the request's `max_tokens`, else `DEFAULT_MAX_OUTPUT_TOKENS`, capped by
the model's maximum, the context window, and any `max_output_tokens` policy. Cached-input
discounts are ignored for the reservation, so it can only overstate. A model without a
price cannot be checked against a hard budget and is refused with `model_unpriced`.

## The reservation script

One Lua script (`budgets/ledger.py`) receives every applicable counter key and, for each,
its limit, mode and TTL. Redis runs it atomically:

1. If any counter is missing, return "hydrate counter i" and change nothing.
2. If any **hard** counter plus the amount would exceed its limit, return "blocked by
   counter i" and change nothing.
3. Otherwise add the amount to every counter (hard and soft) and set TTLs.

Because no other command can run between steps 2 and 3, two requests can never both see
the same remaining balance. This holds across any number of API replicas sharing one Redis.

## Settlement

After the provider answers, the gateway knows the actual cost and adjusts every counter by
`actual - reserved` (usually negative), in the same Redis pipeline that enqueues the usage
event. The adjustment script skips counters that no longer exist, because a rebuilt counter
already reflects the settled spend from Postgres.

| Outcome | Counters | Ledger rows | Usage event |
| --- | --- | --- | --- |
| Success | adjusted to actual | `settled`, actual recorded | SUCCESS, actual cost |
| Provider error status, or never sent | reservation released | `released` | ERROR |
| Sent, no answer (timeout, client disconnect) | reservation **kept** | `uncertain` | UNCERTAIN, then settled at worst case by the worker ([ADR-0006](adr/0006-uncertain-outcomes-are-never-free.md)) |
| Refused by a budget | nothing charged | none | REJECTED, `budget_exceeded` |

## Rebuilding a counter

When a counter is missing, `CounterHydrator` computes, for that budget's scope and window:

```
settled spend (usage_events.actual_cost_nusd)
+ corrections (reconciliation_events for those requests)
+ outstanding reservations (budget_reservations still reserved or uncertain for this counter)
```

and sets it with `SET NX` (so concurrent rebuilds agree), then retries the reservation.
This makes a budget created mid-month count the month's earlier traffic, and makes a Redis
restart safe.

## Proof

| Test | What it proves |
| --- | --- |
| `test_ac2_exhausted_budget_rejects_with_zero_upstream_calls` | A refused request makes zero provider calls (the mock provider counts them) |
| `test_ac3_concurrent_requests_cannot_overspend` | 50 concurrent requests against a budget that fits 10: exactly 10 succeed, 40 get 402, 10 provider calls |
| `test_reservations_settle_to_actual_cost` | The ledger records the worst case, then the actual |
| `test_per_user_budgets_are_independent` | `*` budgets give each end user a separate counter |
| `test_counters_rebuild_from_postgres_after_redis_loss` | After a Redis flush, the counter is rebuilt to the recorded spend |
| `test_ac10_redis_down_fails_closed_for_hard_budgets` | With Redis unreachable, hard-budget requests get 503 and make no provider call |
| `test_ac9_timeout_is_uncertain_and_holds_reservation` | A timeout holds the reservation, then the worker settles it at worst case |

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Redis unreachable | Requests under any hard budget are refused with 503 `budget_service_unavailable`. Requests with only soft budgets, or with `BUDGET_FAILURE_MODE=open`, proceed and are recorded directly to Postgres. Production on AWS refuses to boot with `open`. Key rate limits (`rate_limiter_unavailable`) and stateful policies (`policy_service_unavailable`) also need Redis and return 503 when they apply |
| Redis restarts and loses counters | Counters are rebuilt from Postgres on next use |
| Redis loses data before the worker drains the usage stream | Up to about a second of events (AOF `everysec`) may be missing from recorded spend; counters rebuilt from Postgres then undercount by that amount |
| API process crashes after reserving | The counter stays high until the window ends or it is rebuilt: the safe direction |
| Worker stopped | Budgets keep being enforced (counters live in Redis); recorded spend and dashboards lag until a worker runs |
