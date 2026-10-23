"""SQLAlchemy models for the alerts domain."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="warning")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    budget_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
