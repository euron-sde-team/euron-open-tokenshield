"""SQLAlchemy models for the usage domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin, new_id


class UsageEvent(Base):
    """Append-only. A database trigger refuses UPDATE and DELETE."""

    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="api")
    end_user: Mapped[str | None] = mapped_column(String(200))
    task_id: Mapped[str | None] = mapped_column(String(200), index=True)
    endpoint: Mapped[str] = mapped_column(String(32), nullable=False, default="chat")
    model_alias: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str | None] = mapped_column(String(120))
    upstream_model: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_source: Mapped[str] = mapped_column(String(10), nullable=False, default="none")
    estimated_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    actual_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    avoided_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    price_id: Mapped[int | None] = mapped_column(BigInteger)
    priced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cache_status: Mapped[str] = mapped_column(String(14), nullable=False, default="BYPASS")
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    rule: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_excerpt: Mapped[str | None] = mapped_column(Text)


class ReconciliationEvent(TimestampMixin, Base):
    __tablename__ = "reconciliation_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    delta_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Export(TimestampMixin, Base):
    __tablename__ = "exports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ready")
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class UsageRollupHourly(Base):
    """Pre-aggregated usage per hour and dimension, maintained by the worker.

    Dashboards read rollups for closed hours and raw events only for the current hour, so
    analytics cost stays flat as the event table grows.
    """

    __tablename__ = "usage_rollups_hourly"
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    api_key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    model_alias: Mapped[str] = mapped_column(String(120), primary_key=True)
    provider: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), primary_key=True)
    cache_status: Mapped[str] = mapped_column(String(14), primary_key=True)
    requests: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    avoided_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    latency_ms_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
