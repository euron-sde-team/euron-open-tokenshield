from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from tokenshield.core.schemas import ApiModel

RuleKind = Literal[
    "max_input_tokens",
    "max_output_tokens",
    "restricted_model",
    "prompt_injection",
    "retry_storm",
    "agent_task",
]
Action = Literal["reject", "cap", "throttle", "alert"]
Scope = Literal["global", "team", "project", "api_key", "model"]

# Allowed parameters per rule kind: name -> (type, required)
PARAMS: dict[str, dict[str, tuple[type, bool]]] = {
    "max_input_tokens": {"limit": (int, True)},
    "max_output_tokens": {"limit": (int, True)},
    "restricted_model": {"models": (list, True)},
    "prompt_injection": {"patterns": (list, False)},
    "retry_storm": {"max_repeats": (int, True), "window_s": (int, True)},
    "agent_task": {
        "max_calls": (int, False),
        "max_cost_usd": (float, False),
        "deadline_s": (int, False),
        "max_repeated_tool_calls": (int, False),
    },
}
ACTIONS: dict[str, set[str]] = {
    "max_input_tokens": {"reject", "alert"},
    "max_output_tokens": {"reject", "cap", "alert"},
    "restricted_model": {"reject", "alert"},
    "prompt_injection": {"reject", "alert"},
    "retry_storm": {"throttle", "alert"},
    "agent_task": {"reject", "alert"},
}


def validate_params(kind: str, params: dict[str, Any], action: str) -> dict[str, Any]:
    spec = PARAMS[kind]
    if action not in ACTIONS[kind]:
        raise ValueError(
            f"action '{action}' is not valid for {kind}; use one of {sorted(ACTIONS[kind])}"
        )
    unknown = set(params) - set(spec)
    if unknown:
        raise ValueError(f"unknown parameters for {kind}: {sorted(unknown)}")
    clean: dict[str, Any] = {}
    for name, (typ, required) in spec.items():
        if name not in params or params[name] in (None, ""):
            if required:
                raise ValueError(f"{kind} needs parameter '{name}'")
            continue
        value = params[name]
        if typ is int:
            if isinstance(value, bool) or not isinstance(value, int | float) or value < 1:
                raise ValueError(f"'{name}' must be a positive integer")
            value = int(value)
        elif typ is float:
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise ValueError(f"'{name}' must be a positive number")
            value = float(value)
        elif typ is list:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"'{name}' must be a list of strings")
            if name == "patterns":
                for p in value:
                    try:
                        re.compile(p)
                    except re.error as exc:
                        raise ValueError(f"invalid pattern {p!r}: {exc}") from None
        clean[name] = value
    if kind == "agent_task" and not clean:
        raise ValueError("agent_task needs at least one limit")
    return clean


class RuleIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    kind: RuleKind
    scope_type: Scope = "global"
    scope_id: str | None = Field(None, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)
    action: Action = "reject"
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> RuleIn:
        self.params = validate_params(self.kind, self.params, self.action)
        if self.scope_type == "global":
            self.scope_id = None
        elif not self.scope_id:
            raise ValueError(f"scope_id is required for scope '{self.scope_type}'")
        return self


class RuleUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    params: dict[str, Any] | None = None
    action: Action | None = None
    enabled: bool | None = None


class RuleOut(ApiModel):
    id: uuid.UUID
    name: str
    kind: str
    scope_type: str
    scope_id: str | None
    params: dict[str, Any]
    action: str
    enabled: bool
    triggered_count: int
    created_at: datetime
