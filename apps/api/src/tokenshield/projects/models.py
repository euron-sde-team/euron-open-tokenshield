"""SQLAlchemy models for the projects domain."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin, new_id


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cache_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cache_ttl_s: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    # Sampled output (temperature > 0) differs run to run, so reusing it is opt-in.
    cache_nondeterministic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    semantic_cache_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # None = every enabled model; otherwise the list of permitted aliases.
    allowed_models: Mapped[list[str] | None] = mapped_column(JSONB)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
