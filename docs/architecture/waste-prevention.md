# Waste prevention

Policy rules stop requests that would waste money before any budget is reserved. Static
rules look only at the request and are pure functions (`policies/engine.py`); stateful rules
keep counters in Redis (`policies/stateful.py`). Each rule has a scope (global, team,
project, API key or model) and an action.

| Action | Effect |
| --- | --- |
| `reject` | Stop with a structured error naming the rule (422, or 403 for model access, 429 for agent caps) |
| `cap` | Rewrite the request to fit (output allowance only) |
| `throttle` | Stop with 429 and `Retry-After` (retry storms) |
| `alert` | Let the request through and raise one alert per rule per hour |

## Rules

| Kind | Parameters | Actions | Catches |
| --- | --- | --- | --- |
| `max_input_tokens` | `limit` | reject, alert | Oversized prompts: whole documents pasted in, runaway conversation history |
| `max_output_tokens` | `limit` | reject, cap, alert | Huge `max_tokens` values that inflate reservations and invite long answers. In reject mode, a request that did not ask for an allowance is silently capped instead |
| `restricted_model` | `models` (aliases) | reject, alert | Expensive models used where they should not be |
| `prompt_injection` | `patterns` (regexes, optional) | reject, alert | Known jailbreak phrasings. The built-in list is a heuristic, a tripwire not a guarantee |
| `retry_storm` | `max_repeats`, `window_s` | throttle, alert | The same paid request repeated by one caller (key plus end user) more than `max_repeats` times in `window_s` |
| `agent_task` | any of `max_calls`, `max_cost_usd`, `max_repeated_tool_calls`, `deadline_s` | reject, alert | Runaway agents, keyed by `x-tokenshield-task-id` |

Parameters are validated when a rule is created: unknown parameters, wrong types, invalid
regexes and actions a kind does not support are refused.

## Built-in checks (always on)

These are not rules and cannot be switched off, because they protect correctness:

- **Project model allowlist**: a project with `allowed_models` can call only those aliases
  (403 `model_not_allowed`).
- **Restricted models**: a model marked restricted needs to be on the project's allowlist
  (403 `model_restricted`).
- **Context window**: a prompt at or over the model's context window is refused
  (`context_length_exceeded`); the output allowance is shrunk to fit what remains.
- **Unpriced models under hard budgets** are refused (`model_unpriced`).

## Agent task caps

An agent sends `x-tokenshield-task-id` with every model call for one task. One Lua script
per matching rule checks and updates a Redis hash per task, atomically:

- `max_calls`: the call count would exceed the cap (`agent_call_limit`),
- `deadline_s`: the task is older than the deadline (`agent_deadline`),
- `max_cost_usd`: spent so far plus this call's worst case would exceed the cap
  (`agent_cost_limit`),
- `max_repeated_tool_calls`: the most recent assistant tool call (function name and
  arguments) is identical to the previous request's, that many times in a row
  (`agent_loop_detected`).

Spend is charged to the task after each call, at actual cost. Task state expires after a
day. The dashboard's Agents page lists tasks with their calls, cost, rejections and the
last rule that stopped them.

## Retry storms, and why they ignore cache hits

Many users asking the same popular question is normal traffic, and the cache answers it
for free. So the retry-storm check runs after the cache lookup, only for requests that will
reach the provider, and counts per caller (API key plus end user). A broken client
hammering an uncacheable request is throttled; a classroom asking "what is
photosynthesis?" is not.

## Trigger counts

Each time a rule stops or flags a request, a Redis counter is incremented; the worker
flushes the counts into `policy_rules.triggered_count`, shown on the Policies page.
