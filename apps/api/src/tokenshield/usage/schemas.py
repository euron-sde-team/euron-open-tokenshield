from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from tokenshield.core.schemas import ApiModel, Usd

Range = Literal["1h", "24h", "7d", "30d", "90d"]
Dimension = Literal["model", "provider", "project", "api_key", "status", "cache_status"]


class UsageEventOut(ApiModel):
    id: int
    request_id: str
    created_at: datetime
    project_id: uuid.UUID | None
    project_name: str | None = None
    api_key_id: uuid.UUID | None
    api_key_name: str | None = None
    source: str
    end_user: str | None
    task_id: str | None
    endpoint: str
    model_alias: str | None
    provider: str | None
    upstream_model: str | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_input_tokens: int
    usage_source: str
    estimated_cost_usd: Usd = Field(validation_alias="estimated_cost_nusd")
    actual_cost_usd: Usd = Field(validation_alias="actual_cost_nusd")
    avoided_cost_usd: Usd = Field(validation_alias="avoided_cost_nusd")
    price_id: int | None
    priced: bool
    cache_status: str
    status: str
    rule: str | None
    reason: str | None
    http_status: int
    latency_ms: int
    stream: bool
    prompt_excerpt: str | None


class ReservationOut(ApiModel):
    budget_id: uuid.UUID
    budget_name: str | None = None
    amount_usd: Usd = Field(validation_alias="amount_nusd")
    actual_usd: Usd | None = Field(None, validation_alias="actual_nusd")
    status: str
    created_at: datetime
    settled_at: datetime | None


class ReconciliationOut(ApiModel):
    delta_cost_usd: Usd = Field(validation_alias="delta_cost_nusd")
    reason: str
    created_at: datetime


class UsageEventDetail(UsageEventOut):
    reservations: list[ReservationOut] = []
    reconciliations: list[ReconciliationOut] = []
    price_version: int | None = None


class Totals(ApiModel):
    requests: int = 0
    succeeded: int = 0
    rejected: int = 0
    errors: int = 0
    uncertain: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0
    avoided_usd: float = 0
    avg_latency_ms: float = 0
    cache_hit_rate: float = 0


class Overview(ApiModel):
    range: str
    since: datetime
    totals: Totals
    previous: Totals


class SeriesPoint(ApiModel):
    t: datetime
    requests: int
    cost_usd: float
    avoided_usd: float
    input_tokens: int
    output_tokens: int
    rejected: int
    cache_hits: int


class BreakdownRow(ApiModel):
    key: str
    label: str
    requests: int
    cost_usd: float
    avoided_usd: float
    input_tokens: int
    output_tokens: int
    share: float


class TaskSummary(ApiModel):
    task_id: str
    project_name: str | None
    calls: int
    cost_usd: float
    rejected: int
    first_at: datetime
    last_at: datetime
    last_rule: str | None


class ExportIn(ApiModel):
    range: Range = "30d"
    project_id: uuid.UUID | None = None


class ExportOut(ApiModel):
    id: uuid.UUID
    kind: str
    params: dict[str, object]
    status: str
    rows: int
    bytes: int
    created_at: datetime


class ExportDownload(ApiModel):
    url: str | None = Field(None, description="Presigned URL when storage supports it")
    filename: str
