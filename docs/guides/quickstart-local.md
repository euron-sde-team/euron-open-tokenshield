# Quickstart (local)

Run the whole system on a laptop with only Docker: Postgres, Redis, the AWS emulator
(provisioned by the same Terraform as production), a mock LLM provider, the API, a worker
and the dashboard. No AWS account and no provider keys are needed.

## Prerequisites

- Docker with Compose v2 (Docker Desktop or Docker Engine)
- `make`, `bash`, `openssl`
- For running tests outside containers: Python 3.12 with [uv](https://docs.astral.sh/uv/),
  Node 22 and pnpm 9

## Start

```bash
git clone https://github.com/euron-sde-team/euron-open-tokenshield.git
cd euron-open-tokenshield
make up      # builds images, applies Terraform against Floci, migrates, starts everything
make demo    # demo organisation, 60 days of history, live traffic through the gateway
```

`make up` prints the URLs. `make demo` prints the dashboard login and a gateway key.

| Service | URL |
| --- | --- |
| Dashboard | http://localhost:4110 |
| Gateway (OpenAI-compatible) | http://localhost:4130/v1 |
| API docs (Swagger) | http://localhost:4130/docs |
| Mock LLM provider | http://localhost:4150 |
| Floci (AWS emulator) | http://localhost:4166 |

Ports are overridable in `deploy/compose/.env` (`TS_WEB_PORT`, `TS_API_PORT`,
`TS_MOCK_LLM_PORT`, `TS_PG_PORT`, `TS_REDIS_PORT`, `TS_FLOCI_PORT`).

The first `make up` takes a few minutes: images build, and the Terraform one-shot creates the
exports bucket, KMS key and secrets inside Floci (the S3 lifecycle rule alone takes about a
minute on the emulator). Later starts reuse the state volume.

## Your first request

With the key `make demo` printed:

```bash
curl http://localhost:4130/v1/chat/completions \
  -H "authorization: Bearer tsk_..." \
  -H "content-type: application/json" \
  -d '{"model":"chat-small","temperature":0,"messages":[{"role":"user","content":"What is photosynthesis?"}]}' -i
```

Look at the response headers: `x-tokenshield-cache: MISS`, the cost, the estimate. Send it
again and the cache answers (`HIT`) with zero provider calls.

The same with the OpenAI Python SDK, unmodified:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4130/v1", api_key="tsk_...")
reply = client.chat.completions.create(
    model="chat-small",
    temperature=0,
    messages=[{"role": "user", "content": "What is photosynthesis?"}],
)
print(reply.choices[0].message.content)
```

## Watch the shield work

- **Budget:** in the dashboard, open Budgets, create a hard daily budget of `$0.0005` on the
  Alpha Tutor project, then send a `chat-large` request with that key. It is refused with
  HTTP 402 `budget_exceeded`, and the mock provider never sees it.
- **Retry storm:** send the same request with `"temperature": 0.8` seven times in a minute.
  The demo's retry-storm rule throttles it with 429 and `Retry-After`.
- **Agent loop:** send requests to the Code Review Agent project with the same
  `x-tokenshield-task-id`. After 12 calls the task is stopped with `agent_call_limit`.
- **Playground:** run any request from the dashboard and see the cache result and cost
  headers inline.

## Stop

```bash
make down    # stops containers and deletes their volumes
```

## Next

- [Integrate your application](integrate.md)
- [Configuration reference](configuration.md)
- [Testing](testing.md)
- [Deploy to AWS](deploy-aws.md)
