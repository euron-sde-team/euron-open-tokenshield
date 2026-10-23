"""SQLAlchemy models for the providers domain."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin, new_id


class Provider(TimestampMixin, Base):
    __tablename__ = "providers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # openai | anthropic
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    sealed_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_hint: Mapped[str | None] = mapped_column(String(16))
    timeout_s: Mapped[float | None] = mapped_column(Numeric(6, 1))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Model(TimestampMixin, Base):
    __tablename__ = "models"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    alias: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False
    )
    upstream_model: Mapped[str] = mapped_column(String(200), nullable=False)
    tokenizer: Mapped[str] = mapped_column(String(32), nullable=False, default="o200k_base")
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=128000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=16384)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")  # chat|embedding
    restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
