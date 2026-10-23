# Architecture Decision Records

Each ADR captures one significant decision: the context that forced it, what we chose,
and what it costs us. ADRs are immutable once accepted. To revisit one, write a new ADR
that supersedes it.

| ADR | Decision | Status |
| --- | -------- | ------ |
| [0001](0001-single-tenant-deployments.md) | One deployment serves one organisation; teams, projects and keys live inside it | Accepted |
| [0002](0002-atomic-budget-reservations-in-redis.md) | Hard budgets are enforced by reserving worst-case cost in one Redis Lua script | Accepted |
| [0003](0003-integer-nano-dollars.md) | Money is integer nano-dollars everywhere inside the system | Accepted |
| [0004](0004-usage-events-through-a-redis-stream.md) | Usage events go through a Redis Stream, drained to Postgres by workers | Accepted |
| [0005](0005-local-aws-emulation.md) | Local AWS emulator (Floci), provisioned by the same Terraform as production | Accepted |
| [0006](0006-uncertain-outcomes-are-never-free.md) | A request whose outcome is unknown keeps its reservation and is settled at worst case | Accepted |
| [0007](0007-python-fastapi-and-nextjs.md) | Python and FastAPI for the gateway, Next.js for the dashboard | Accepted |
| [0008](0008-exact-cache-first-semantic-behind-a-flag.md) | Exact-match caching by default; semantic caching behind a flag | Accepted |

**Template:** Status / Date, then Context, Decision, Consequences (good and bad), and
Alternatives considered.
