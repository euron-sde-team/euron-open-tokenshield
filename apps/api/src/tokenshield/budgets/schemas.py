from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from tokenshield.core.schemas import ApiModel

ScopeType = Literal["global", "team", "project", "api_key", "end_user", "model"]
Period = Literal["daily", "weekly", "monthly", "total"]
Mode = Literal["hard", "soft"]


class BudgetIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    scope_type: ScopeType
    scope_id: str | None = Field(
        None,
        max_length=200,
        description="Team/project/key id, end-user id ('*' = each user separately), or model alias",
    )
    period: Period
    limit_usd: Decimal = Field(gt=0, le=10_000_000)
    mode: Mode = "hard"
    alert_threshold_pct: int = Field(80, ge=1, le=100)
    enabled: bool = True

    @model_validator(mode="after")
    def _scope(self) -> BudgetIn:
        if self.scope_type == "global":
            self.scope_id = None
        elif not self.scope_id:
            raise ValueError(f"scope_id is required for scope '{self.scope_type}'")
        return self


class BudgetUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    limit_usd: Decimal | None = Field(None, gt=0, le=10_000_000)
    mode: Mode | None = None
    alert_threshold_pct: int | None = Field(None, ge=1, le=100)
    enabled: bool | None = None


class BudgetOut(ApiModel):
    id: uuid.UUID
    name: str
    scope_type: str
    scope_id: str | None
    scope_label: str | None = None
    period: str
    limit_usd: float
    mode: str
    alert_threshold_pct: int
    enabled: bool
    created_at: datetime
    window_start: datetime | None = None
    window_end: datetime | None = None
    spent_usd: float | None = Field(
        None, description="Settled spend plus in-flight reservations in the current window"
    )
    used_pct: float | None = None
