# ADR-0003: Money is integer nano-dollars

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

LLM requests are cheap individually and expensive in aggregate. A small model call can
cost a few millionths of a dollar; a month of traffic can cost thousands. Budgets compare
sums of many tiny amounts to a limit, and reservations are added and subtracted many
times. Floats drift; decimals do not fit Redis counters.

## Decision

All amounts inside the system are integers in nano-dollars (1 USD = 1,000,000,000 nUSD):
Postgres `BIGINT` columns, Redis counters, and Python `int`. Prices are stored as
`NUMERIC(14,6)` USD per million tokens and converted by `core/money.py`, rounding **up**,
so an estimate can only overstate a cost. The API converts to USD floats only at the edge
(the `Usd` schema type).

## Consequences

**Good**
- Exact arithmetic for reservations and settlements; `INCRBY` works natively.
- A `BIGINT` still holds over nine billion dollars, far beyond any budget.
- One rule for contributors: no floats for money inside the API.

**Bad / caveats**
- Sub-nano-dollar costs round up to 1 nUSD. At current prices that is far below any
  meaningful amount.
- Readers of the raw database see large integers; the dashboard and API always show USD.

## Alternatives considered

- **Floats.** Rejected: drift in sums and comparisons.
- **Python `Decimal` everywhere.** Rejected: does not survive the trip through Redis.
- **Micro-dollars.** Rejected: too coarse for cached-token pricing on small models.
