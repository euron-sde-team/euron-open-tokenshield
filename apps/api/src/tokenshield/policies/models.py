"""SQLAlchemy models for the policies domain."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin, new_id


class PolicyRule(TimestampMixin, Base):
    __tablename__ = "policy_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # max_input_tokens | max_output_tokens | retry_storm | agent_task | restricted_model
    # | prompt_injection
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="global")
    scope_id: Mapped[str | None] = mapped_column(String(200))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    action: Mapped[str] = mapped_column(String(10), nullable=False, default="reject")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    triggered_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
