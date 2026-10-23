# ADR-0008: Exact-match caching by default, semantic caching behind a flag

- **Status:** Accepted
- **Date:** 2026-10-23

## Context

Reusing an LLM answer saves its full cost, but serving a wrong or someone else's answer is
worse than paying. Exact-match caching is provably correct when the key covers everything
that affects the answer. Semantic caching (reusing an answer to a differently worded
question) saves more, but its correctness depends on an embedding model and a similarity
threshold, and its privacy depends on never comparing across contexts.

## Decision

- Exact-match caching is on by default for eligible requests. The key hashes the model
  alias, every generation parameter, the full message list, tools and output schema, and a
  partition: the project plus an optional caller-declared scope (an end user or a context
  version).
- Only deterministic requests are eligible by default (`temperature` 0); a project can opt
  in to caching sampled output. Requests marked `x-tokenshield-cache: off`, `n > 1` or
  `logprobs` are never cached. Only complete text answers are stored.
- Semantic caching requires `SEMANTIC_CACHE=true` on the server **and** opt-in per project.
  It embeds only the final user turn; everything else (system prompt, earlier turns, tools,
  parameters) must match exactly through a partition hash, so a similar question in a
  different context can never match.

## Consequences

**Good**
- Correct by construction for the default path, with cross-project and cross-user leaks
  covered by integration tests.
- Semantic caching is available for FAQ-style workloads without being a default risk.

**Bad / caveats**
- Exact matching misses rephrased questions unless semantic caching is enabled.
- Semantic search is a brute-force nearest-neighbour query within one partition; partitions
  are small in practice, and an approximate index is on the roadmap.

## Alternatives considered

- **Semantic caching by default.** Rejected: threshold tuning and embedding quality become
  correctness concerns for every user.
- **No caching.** Rejected: identical repeated questions are common and pure waste.
