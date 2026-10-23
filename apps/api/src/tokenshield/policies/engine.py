"""Waste-prevention policy engine.

Static rules look only at the request (size, output allowance, model, content) and are
pure functions, so they are cheap and exhaustively unit tested. Stateful rules (retry
storms, agent task caps) keep counters in Redis and live in ``policies.stateful``.

Rule actions:
  reject    stop the request with a structured error
  cap       rewrite the request to fit (only for output allowance)
  throttle  stop with 429 and Retry-After (stateful rules)
  alert     let the request through, record an alert
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

from tokenshield.gateway.catalog import RuleInfo

RULE_KINDS = (
    "max_input_tokens",
    "max_output_tokens",
    "restricted_model",
    "prompt_injection",
    "retry_storm",
    "agent_task",
)
ACTIONS = ("reject", "cap", "throttle", "alert")

DEFAULT_INJECTION_PATTERNS = (
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts|rules)",
    r"disregard (the |your )?(system|previous) (prompt|instructions)",
    r"(reveal|print|show|repeat) (me )?(your|the) (system prompt|hidden instructions)",
    r"you are now (dan|in developer mode|unrestricted)",
    r"pretend (that )?you have no (rules|restrictions|guidelines)",
)


@dataclass(frozen=True, slots=True)
class Violation:
    rule_id: str | None
    rule_name: str
    kind: str
    action: str
    code: str
    message: str
    status: int = 422
    retry_after_s: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RequestFacts:
    project_id: str
    team_id: str | None
    api_key_id: str | None
    model_alias: str
    model_restricted: bool
    allowed_models: tuple[str, ...] | None
    input_tokens: int
    requested_max_output: int | None
    model_max_output: int
    context_window: int
    default_max_output: int
    user_texts: tuple[str, ...] = ()


@dataclass(slots=True)
class StaticOutcome:
    max_output_tokens: int
    output_capped: bool = False
    block: Violation | None = None
    alerts: list[Violation] = field(default_factory=list)


def applies(rule: RuleInfo, facts: RequestFacts) -> bool:
    match rule.scope_type:
        case "global":
            return True
        case "team":
            return facts.team_id is not None and rule.scope_id == facts.team_id
        case "project":
            return rule.scope_id == facts.project_id
        case "api_key":
            return facts.api_key_id is not None and rule.scope_id == facts.api_key_id
        case "model":
            return rule.scope_id == facts.model_alias
    return False


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _violation(rule: RuleInfo, code: str, message: str, **details: Any) -> Violation:
    return Violation(
        rule_id=str(rule.id),
        rule_name=rule.name,
        kind=rule.kind,
        action=rule.action,
        code=code,
        message=message,
        details=details,
    )


def evaluate_static(rules: Iterable[RuleInfo], facts: RequestFacts) -> StaticOutcome:
    # The output allowance is what the caller asked for, else the gateway default, never
    # more than the model supports. Reservations are priced on this number.
    requested = facts.requested_max_output
    max_out = min(requested or facts.default_max_output, facts.model_max_output)
    outcome = StaticOutcome(max_output_tokens=max_out, output_capped=False)

    # Model access is not a rule toggle: a restricted model needs an explicit allowance.
    if facts.allowed_models is not None and facts.model_alias not in facts.allowed_models:
        outcome.block = Violation(
            None,
            "project model allowlist",
            "restricted_model",
            "reject",
            "model_not_allowed",
            f"Model '{facts.model_alias}' is not enabled for this project",
            status=403,
            details={"model": facts.model_alias},
        )
        return outcome
    if facts.model_restricted and (
        facts.allowed_models is None or facts.model_alias not in facts.allowed_models
    ):
        outcome.block = Violation(
            None,
            "restricted model",
            "restricted_model",
            "reject",
            "model_restricted",
            f"Model '{facts.model_alias}' is restricted; add it to the project's allowed "
            "models to use it",
            status=403,
            details={"model": facts.model_alias},
        )
        return outcome

    if facts.input_tokens >= facts.context_window:
        outcome.block = Violation(
            None,
            "context window",
            "max_input_tokens",
            "reject",
            "context_length_exceeded",
            f"Prompt is about {facts.input_tokens} tokens; model context window is "
            f"{facts.context_window}",
            details={"input_tokens": facts.input_tokens, "context_window": facts.context_window},
        )
        return outcome
    room = facts.context_window - facts.input_tokens
    if outcome.max_output_tokens > room:
        outcome.max_output_tokens = room
        outcome.output_capped = True

    for rule in rules:
        if not applies(rule, facts):
            continue
        violation: Violation | None = None
        if rule.kind == "max_input_tokens":
            limit = int(rule.params.get("limit", 0))
            if limit and facts.input_tokens > limit:
                violation = _violation(
                    rule,
                    "prompt_too_large",
                    f"Prompt is about {facts.input_tokens} tokens; the limit is {limit}. "
                    "Trim the context or summarise earlier turns",
                    input_tokens=facts.input_tokens,
                    limit=limit,
                )
        elif rule.kind == "max_output_tokens":
            limit = int(rule.params.get("limit", 0))
            if limit and outcome.max_output_tokens > limit:
                if rule.action == "cap":
                    outcome.max_output_tokens = limit
                    outcome.output_capped = True
                    continue
                if requested is not None:
                    violation = _violation(
                        rule,
                        "output_limit_exceeded",
                        f"max_tokens {requested} exceeds the limit of {limit}",
                        requested=requested,
                        limit=limit,
                    )
                else:
                    outcome.max_output_tokens = limit
        elif rule.kind == "restricted_model":
            models = rule.params.get("models") or []
            if facts.model_alias in models:
                violation = _violation(
                    rule,
                    "model_restricted",
                    f"Model '{facts.model_alias}' is restricted by policy '{rule.name}'",
                    model=facts.model_alias,
                )
                violation = replace(violation, status=403)
        elif rule.kind == "prompt_injection":
            patterns = list(rule.params.get("patterns") or []) or list(DEFAULT_INJECTION_PATTERNS)
            text = "\n".join(facts.user_texts)
            hit = next((p for p in patterns if _compile(p).search(text)), None)
            if hit:
                violation = _violation(
                    rule,
                    "prompt_injection_suspected",
                    "The prompt matches a configured injection pattern",
                    pattern=hit,
                )
        if violation is None:
            continue
        if violation.action == "alert":
            outcome.alerts.append(violation)
        else:
            outcome.block = violation
            return outcome
    return outcome
