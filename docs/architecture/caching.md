# Caching

TokenShield caches at five layers. Two of them save provider spend (the response cache and
the semantic cache); the other three keep the gateway and the dashboard off the database.
The design decision for response caching is
[ADR-0008](adr/0008-exact-cache-first-semantic-behind-a-flag.md).

| Layer | What | Where | Key | Lifetime and invalidation |
| --- | --- | --- | --- | --- |
| Response cache | Chat completion bodies (zlib-compressed above 1 KB) | Redis `ts:cache:body:{key}` | SHA-256 of the normalised request plus partition | Project TTL (`cache_ttl_s`); invalidate one entry or purge a project from the dashboard |
| Semantic cache | Embeddings of final user turns | Postgres `semantic_cache` (pgvector) | Partition hash | Same TTL; removed with the exact entry; expired rows purged hourly |
| Gateway config | Key lookups, models, prices, projects, budgets, rules | In-process, per API instance | `catalog`, `key:{prefix}` | 5 s TTL, and any admin write bumps `ts:cfg:version`; every instance checks the stamp at most once a second, so a revoked key stops working cluster-wide within about a second |
| Analytics | Overview, time series, breakdowns | Redis `ts:an:*` | Query parameters | 10 s |
| Dashboard | Server state | TanStack Query in the browser | Per resource | `staleTime` per view, invalidated after each mutation |

## Response cache key

`cache/keys.py exact_key` hashes, with sorted keys:

- the model **alias** (not the upstream model, so re-pointing an alias starts fresh only if
  you purge; see Operations),
- every parameter that changes the answer: `temperature`, `top_p`, `max_tokens`,
  `max_completion_tokens`, `stop`, `seed`, `n`, penalties, `logit_bias`, `logprobs`,
  `tools`, `tool_choice`, `parallel_tool_calls`, `response_format`, `reasoning_effort`,
- the full message list (role, content with surrounding whitespace trimmed, name,
  tool calls, tool call ids),
- the **partition**: a hash of the project id and the caller's declared scope.

Fields that do not change the answer (`user`, `stream`, metadata) are excluded, so a
streamed and a non-streamed request share an entry, and a cached answer can be replayed as
an SSE stream.

## Partitions: who may share an answer

| `x-tokenshield-cache-scope` | Partition | Use it when |
| --- | --- | --- |
| absent | the project | Answers depend only on the prompt (FAQ, public content) |
| `user` | the project and `x-tokenshield-user` | Answers depend on the user's own data. Without a user id the request is not cached at all |
| any other value | the project and that value | Answers depend on a context version, a document set or a permission group |

Two projects never share an entry. The integration tests
`test_ac6_user_scoped_cache_never_crosses_users` and `test_ac6_projects_never_share_entries`
prove both.

## Eligibility

A request is looked up and stored only when all of these hold:

- the project has caching on, and the request does not send
  `x-tokenshield-cache: off` (also `no-store`, `bypass`, `false`, `0`),
- `temperature` is 0, or the project opts in to caching sampled output (OpenAI's default
  temperature is 1, so an absent temperature counts as sampled),
- `n` is 1 and `logprobs` is not requested.

Only complete text answers are stored: `finish_reason` `stop`, no tool calls. Tool calls
drive agent state, and replaying one could hide a loop from the agent rules.

Cache hits never bypass the shield: authentication, model access, static policies, rate
limits and agent task caps run before the lookup. Retry-storm counting runs only on the
paid path, because repeats answered from cache cost nothing.

## Coalescing

On a miss, a non-streaming request runs one script that either returns the cached body or
takes a short lock (`SET NX PX`, `COALESCE_WAIT_S`). The lock holder calls the provider.
Identical requests that arrive meanwhile poll for the cached result with backoff and are
answered with `COALESCED` and zero provider calls. If the leader fails, it releases the
lock and a waiter takes over, so followers are never stranded
(`test_ac7_identical_concurrent_requests_coalesce`, `test_failed_leader_releases_followers`).

## Semantic cache

Off unless `SEMANTIC_CACHE=true` on the server and `semantic_cache_enabled` on the project.
On an exact miss, the final user turn is embedded with `SEMANTIC_EMBEDDING_MODEL` through
the gateway's own provider adapters, and the nearest stored vector in the same partition is
compared by cosine similarity against `SEMANTIC_THRESHOLD`. The partition includes a hash
of everything except the final user turn (system prompt, earlier turns, tools, parameters),
so the same question in a different context never matches
(`test_semantic_cache_respects_context`).

## What is reported

A hit records a usage event with `actual_cost_nusd = 0` and `avoided_cost_nusd` equal to
what the cached answer cost at the current price. Hit counts, tokens saved and avoided cost
are buffered in Redis and flushed to `cache_entries` by the worker. The dashboard reports
**spend avoided**, not net savings: cache infrastructure and embedding calls are not
subtracted.
