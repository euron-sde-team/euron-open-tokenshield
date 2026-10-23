"""SQLAlchemy models for the budgets domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tokenshield.core.db import Base, TimestampMixin, new_id


class Budget(TimestampMixin, Base):
    __tablename__ = "budgets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # global | team | project | api_key | end_user | model
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # team/project/api_key: uuid as text. end_user: the end-user id ("*" = each user).
    # model: the alias. global: null.
    scope_id: Mapped[str | None] = mapped_column(String(200))
    period: Mapped[str] = mapped_column(String(8), nullable=False)  # daily|weekly|monthly|total
    limit_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="hard")  # hard|soft
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BudgetReservation(TimestampMixin, Base):
    __tablename__ = "budget_reservations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    counter_key: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_nusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_nusd: Mapped[int | None] = mapped_column(BigInteger)
    # reserved | settled | released | uncertain
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="reserved")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
