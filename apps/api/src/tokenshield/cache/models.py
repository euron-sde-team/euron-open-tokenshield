"""SQLAlchemy models for the cache domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin


class CacheEntry(TimestampMixin, Base):
    """Statistics for a cached response. The body itself lives in Redis with its TTL."""

    __tablename__ = "cache_entries"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    model_alias: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="exact")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tokens_saved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    avoided_cost_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    prompt_excerpt: Mapped[str | None] = mapped_column(Text)
    invalidated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SemanticCacheEntry(TimestampMixin, Base):
    __tablename__ = "semantic_cache"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    partition: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
