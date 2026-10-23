# Integrate an application

TokenShield speaks the OpenAI chat-completions API. Point any OpenAI SDK, LangChain,
LlamaIndex or plain HTTP client at `<gateway>/v1` with a TokenShield key, and use model
**aliases** configured on the Models page. Nothing else changes.

## Python

```python
from openai import OpenAI

client = OpenAI(base_url="https://tokenshield.example.com/v1", api_key="tsk_...")
resp = client.chat.completions.create(
    model="chat-small",
    messages=[{"role": "user", "content": "Summarise this ticket"}],
    extra_headers={"x-tokenshield-user": "customer-8812"},
)
```

## TypeScript

```ts
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "https://tokenshield.example.com/v1", apiKey: "tsk_..." });
const stream = await client.chat.completions.create(
  { model: "claude-sonnet", messages: [{ role: "user", content: "Draft a reply" }], stream: true },
  { headers: { "x-tokenshield-task-id": "ticket-4412" } },
);
for await (const chunk of stream) process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
```

Streaming works for every provider, including Anthropic models behind the OpenAI shape.
TokenShield asks OpenAI-compatible providers for a final usage chunk, so streamed calls
are billed from provider-reported tokens.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/v1/chat/completions` | Streaming and non-streaming |
| POST | `/v1/embeddings` | Attributed, limited and budgeted; not cached |
| GET | `/v1/models` | The aliases this key's project may use |

## Request headers

| Header | Effect |
| --- | --- |
| `Authorization: Bearer tsk_...` (or `x-api-key`) | Required. The key decides the project and its limits |
| `x-tokenshield-user` | End-user id for per-user budgets, user-scoped caching and attribution. The OpenAI `user` field is used when this header is absent |
| `x-tokenshield-task-id` | Groups an agent's calls for agent task caps |
| `x-tokenshield-cache: off` | Never read or write the cache for this request (sensitive prompts) |
| `x-tokenshield-cache-scope` | `user` shares cache entries only within one end user; any other value names a context (a document version, a permission group) |
| `Idempotency-Key` | Retries with the same key return the stored response without a second provider call, and are never double counted. A duplicate still in flight gets 409 |

## Response headers

| Header | Meaning |
| --- | --- |
| `x-tokenshield-request-id` | Find the request in the dashboard's request log |
| `x-tokenshield-cache` | `MISS`, `HIT`, `SEMANTIC_HIT`, `COALESCED` or `BYPASS` |
| `x-tokenshield-cost-usd` | Actual cost from provider-reported usage |
| `x-tokenshield-estimated-cost-usd` | The worst case that was reserved |
| `x-tokenshield-avoided-cost-usd` | On cache hits: the spend avoided |
| `x-tokenshield-priced: false` | The model has no price in the catalog |
| `x-tokenshield-idempotent-replay: true` | Served from an earlier response with the same Idempotency-Key |

## Errors

Errors use the OpenAI envelope with extra structure:
`{"error": {"code", "type", "message", "details"}}`. SDKs surface `message` and `code`.

| HTTP | `code` | When |
| --- | --- | --- |
| 401 | `invalid_api_key`, `api_key_revoked`, `api_key_expired` | Bad or retired key |
| 402 | `budget_exceeded` | A hard budget cannot cover the worst-case cost. `details` names the budget, limit, spend, remaining and estimate |
| 403 | `model_not_allowed`, `model_restricted`, `project_unavailable` | Model access or archived project |
| 404 | `model_not_found` | Unknown alias |
| 409 | `request_in_progress` | Same Idempotency-Key still running |
| 422 | `prompt_too_large`, `context_length_exceeded`, `output_limit_exceeded`, `prompt_injection_suspected`, `model_unpriced` | Policy refusals before any spend |
| 429 | `rpm_limit`, `tpm_limit`, `concurrency_limit`, `retry_storm`, `agent_call_limit`, `agent_cost_limit`, `agent_loop_detected`, `agent_deadline` | Limits and waste rules; `Retry-After` is set where a wait helps |
| 4xx | provider status | The provider refused the request (400, 401, 403, 404, 409, 422, 429 pass through) |
| 502 | `upstream_error` | Provider error or unreachable; any reservation was released |
| 503 | `budget_service_unavailable`, `rate_limiter_unavailable`, `policy_service_unavailable` | Redis unavailable; refused rather than unchecked |
| 504 | `upstream_timeout` | The provider did not answer in time; the cost is held until reconciled |

## Patterns

- **Agents:** send a stable `x-tokenshield-task-id` per task and add an `agent_task` rule.
  Handle 429 `agent_*` codes by ending the task, not retrying.
- **Retries:** send an `Idempotency-Key` for anything you might retry; honour `Retry-After`.
- **Per-user features:** send `x-tokenshield-user` and use `x-tokenshield-cache-scope: user`
  when answers depend on the user's own data.
