"""Stateful waste rules backed by Redis: retry storms and agent task caps."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from typing import Any

import orjson
from redis.asyncio import Redis

from tokenshield.core.money import nusd_to_usd, usd_to_nusd
from tokenshield.gateway.catalog import RuleInfo
from tokenshield.policies.engine import RequestFacts, Violation, applies

TASK_TTL_S = 86400

# KEYS[1] task hash. ARGV: now, max_calls, max_cost_nusd, deadline_s, tool_fp,
# max_repeats, estimate_nusd. A zero limit disables that check.
# Returns {code, value}: code 0 ok, 1 calls, 2 cost, 3 deadline, 4 loop.
_TASK = """
local now = tonumber(ARGV[1])
local max_calls = tonumber(ARGV[2])
local max_cost = tonumber(ARGV[3])
local deadline = tonumber(ARGV[4])
local tool_fp = ARGV[5]
local max_repeats = tonumber(ARGV[6])
local estimate = tonumber(ARGV[7])
local first = tonumber(redis.call('HGET', KEYS[1], 'first') or now)
local calls = tonumber(redis.call('HGET', KEYS[1], 'calls') or '0')
local cost = tonumber(redis.call('HGET', KEYS[1], 'cost') or '0')
local last_fp = redis.call('HGET', KEYS[1], 'tool_fp') or ''
local repeats = tonumber(redis.call('HGET', KEYS[1], 'repeats') or '0')
if max_calls > 0 and calls + 1 > max_calls then return {1, calls} end
if deadline > 0 and now - first > deadline then return {3, now - first} end
if max_cost > 0 and cost + estimate > max_cost then return {2, cost} end
if tool_fp ~= '' and tool_fp == last_fp then repeats = repeats + 1 else repeats = 0 end
if max_repeats > 0 and repeats >= max_repeats then return {4, repeats} end
redis.call('HSET', KEYS[1], 'first', first, 'calls', calls + 1, 'tool_fp', tool_fp,
  'repeats', repeats)
redis.call('EXPIRE', KEYS[1], ARGV[8])
return {0, calls + 1}
"""


def tool_call_fingerprint(body: dict[str, Any]) -> str:
    """Fingerprint of the most recent assistant tool calls in the conversation.

    An agent stuck in a loop sends back the same tool call (same function, same
    arguments) turn after turn; that repetition is what the loop rule counts.
    """
    for msg in reversed(body.get("messages") or []):
        if msg.get("role") == "assistant":
            calls = msg.get("tool_calls")
            if not calls:
                return ""
            norm = sorted(
                (
                    (c.get("function") or {}).get("name", ""),
                    (c.get("function") or {}).get("arguments", ""),
                )
                for c in calls
            )
            return hashlib.sha256(orjson.dumps(norm)).hexdigest()[:24]
    return ""


class StatefulPolicies:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._task = redis.register_script(_TASK)

    async def check_retry_storm(
        self,
        rules: Iterable[RuleInfo],
        facts: RequestFacts,
        fingerprint: str,
        end_user: str | None = None,
    ) -> tuple[Violation | None, list[Violation]]:
        alerts: list[Violation] = []
        for rule in rules:
            if rule.kind != "retry_storm" or not applies(rule, facts):
                continue
            window = int(rule.params.get("window_s", 60))
            max_repeats = int(rule.params.get("max_repeats", 5))
            subject = f"{facts.api_key_id or facts.project_id}:{end_user or ''}"
            key = f"ts:rs:{rule.id}:{subject}:{fingerprint}"
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
            if int(count) <= max_repeats:
                continue
            violation = Violation(
                str(rule.id),
                rule.name,
                rule.kind,
                "throttle" if rule.action == "throttle" else rule.action,
                "retry_storm",
                f"The same request was sent {count} times in {window}s (limit {max_repeats}). "
                "Back off before retrying",
                status=429,
                retry_after_s=max(1, int(ttl)),
                details={"count": int(count), "window_s": window, "max_repeats": max_repeats},
            )
            if rule.action == "alert":
                alerts.append(violation)
            else:
                return violation, alerts
        return None, alerts

    async def check_agent_task(
        self,
        rules: Iterable[RuleInfo],
        facts: RequestFacts,
        task_id: str | None,
        body: dict[str, Any],
        estimate_nusd: int,
    ) -> tuple[Violation | None, list[Violation], list[str]]:
        """Returns (block, alerts, task keys to charge after the call)."""
        if not task_id:
            return None, [], []
        alerts: list[Violation] = []
        keys: list[str] = []
        fp = tool_call_fingerprint(body)
        for rule in rules:
            if rule.kind != "agent_task" or not applies(rule, facts):
                continue
            p = rule.params
            key = f"ts:task:{rule.id}:{facts.project_id}:{task_id}"
            code, value = await self._task(
                keys=[key],
                args=[
                    int(time.time()),
                    int(p.get("max_calls", 0)),
                    usd_to_nusd(p.get("max_cost_usd", 0)),
                    int(p.get("deadline_s", 0)),
                    fp,
                    int(p.get("max_repeated_tool_calls", 0)),
                    estimate_nusd,
                    TASK_TTL_S,
                ],
            )
            code = int(code)
            if code == 0:
                keys.append(key)
                continue
            messages = {
                1: (
                    "agent_call_limit",
                    f"Task '{task_id}' reached its limit of {p.get('max_calls')} model calls",
                ),
                2: (
                    "agent_cost_limit",
                    f"Task '{task_id}' has spent "
                    f"${nusd_to_usd(int(value)):.4f} of its ${p.get('max_cost_usd')} cap",
                ),
                3: (
                    "agent_deadline",
                    f"Task '{task_id}' exceeded its {p.get('deadline_s')}s deadline",
                ),
                4: (
                    "agent_loop_detected",
                    f"Task '{task_id}' repeated the same tool call {value} times in a row",
                ),
            }
            err_code, message = messages[code]
            violation = Violation(
                str(rule.id),
                rule.name,
                rule.kind,
                rule.action,
                err_code,
                message,
                status=429,
                details={"task_id": task_id, "rule": rule.name},
            )
            if rule.action == "alert":
                alerts.append(violation)
                keys.append(key)
            else:
                return violation, alerts, keys
        return None, alerts, keys

    async def charge_tasks(self, keys: Iterable[str], cost_nusd: int) -> None:
        for key in keys:
            await self._redis.hincrby(key, "cost", cost_nusd)
