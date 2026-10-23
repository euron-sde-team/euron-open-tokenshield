"""SQLAlchemy models for the pricing domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin


class ModelPrice(TimestampMixin, Base):
    """One immutable price version for a model. Usage rows reference the version they used."""

    __tablename__ = "model_prices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    cached_input_per_m: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    output_per_m: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
