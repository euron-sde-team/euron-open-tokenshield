"""Alerts raised by soft budgets, budget thresholds and alert-only policy rules.

Each alert carries a dedupe key (rule or budget + window), so a rule firing a thousand
times in an hour produces one alert, not a thousand rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from tokenshield.alerts.models import Alert


class AlertService:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sessionmaker = sessionmaker

    async def raise_alert(
        self,
        kind: str,
        message: str,
        *,
        dedupe_key: str,
        severity: str = "warning",
        budget_id: uuid.UUID | None = None,
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                insert(Alert)
                .values(
                    kind=kind,
                    message=message,
                    severity=severity,
                    budget_id=budget_id,
                    dedupe_key=dedupe_key,
                )
                .on_conflict_do_nothing(index_elements=["dedupe_key"])
            )
