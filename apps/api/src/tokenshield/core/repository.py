"""Generic repository base. Domain repositories extend it with their own queries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.core.db import Base


class Repository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: Any) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def list(self, stmt: Select[tuple[ModelT]] | None = None) -> Sequence[ModelT]:
        result = await self.session.scalars(stmt if stmt is not None else select(self.model))
        return result.all()

    async def count(self, stmt: Select[Any]) -> int:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        return int(total or 0)

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()
