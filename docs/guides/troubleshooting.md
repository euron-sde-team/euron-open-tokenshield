# Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every request returns 503 `budget_service_unavailable` | Redis is unreachable and the request falls under a hard budget. TokenShield refuses rather than spend unchecked | Restore Redis (`/readyz` shows which dependency is down). `BUDGET_FAILURE_MODE=open` trades spend control for availability and is refused on AWS |
| 422 `model_unpriced` | The model has no price and a hard budget applies, so its cost cannot be checked | Publish a price on the Models page (a price of 0 is valid for local models) |
| 402 `budget_exceeded` although the budget looks unused | The reservation is the worst case: the full output allowance at the output price. A large `max_tokens` on an expensive model can exceed a small budget on its own | Lower `max_tokens`, add a `max_output_tokens` cap rule, or raise the budget. `details.estimated_cost_usd` shows the reservation |
| A request was blocked for a model the project should use | `model_not_allowed` (the project has an allowlist) or `model_restricted` (the model is marked restricted) | Edit the project's allowed models |
| Identical requests are never cache hits | Not eligible: `temperature` absent or above 0, `x-tokenshield-cache: off`, `n > 1`, user scope without a user id, or the project has caching off | Send `temperature: 0`, or enable "Cache non-deterministic" on the project |
| Requests appear in the log late, or not at all | No worker is draining the usage stream | Start `tokenshield worker` (in Compose: `make logs SERVICE=worker`) |
| A revoked key still worked for a moment | Instances refresh configuration within about a second of a change | Expected; for an emergency, revoke and wait one second |
| Spend shows an amount for a request that failed | It timed out after being sent (`UNCERTAIN`); the provider may have billed it, so it is settled at its reserved worst case after 15 minutes | Expected. See [ADR-0006](../architecture/adr/0006-uncertain-outcomes-are-never-free.md) |
| 429 `retry_storm` from a well-behaved client | The same paid request was repeated more than the rule allows within its window | Raise `max_repeats`, send an `Idempotency-Key` for retries, or vary the request |
| "Too many sign-in attempts from this address" | 20 sign-ins per minute per IP | Wait a minute; automated tests should reuse a session |
| `make up` is slow the first time | Images build and Terraform creates resources in Floci (the S3 lifecycle rule takes about a minute on the emulator) | Later starts reuse the Terraform state volume |
| Port already in use | Another service owns 4110, 4130, 4142, 4150, 4166 or 4179 | Set `TS_*_PORT` in `deploy/compose/.env` |
| Integration tests refuse to run | The database name lacks `test`, or the host is not local | Use `TEST_DATABASE_URL` pointing at a `*_test` database; `ALLOW_REMOTE_TEST_DB=true` for CI hosts |
| `make test-matrix` says Floci is not reachable | The stack is not running | `make up` first |
