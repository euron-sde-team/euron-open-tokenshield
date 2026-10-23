"""Cache administration: inspect entries, see savings, purge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import case, func, select, update

from tokenshield.audit.service import audit
from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.cache.models import CacheEntry
from tokenshield.cache.semantic import SemanticIndex
from tokenshield.cache.store import ResponseCache
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.core.errors import NotFoundError
from tokenshield.core.money import nusd_to_usd
from tokenshield.core.schemas import ApiModel, Message, Usd
from tokenshield.projects.models import Project

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


class CacheEntryOut(ApiModel):
    key_hash: str
    project_id: uuid.UUID | None
    project_name: str | None = None
    model_alias: str
    kind: str
    created_at: datetime
    expires_at: datetime
    hits: int
    last_hit_at: datetime | None
    tokens_saved: int
    avoided_cost_usd: Usd = Field(validation_alias="avoided_cost_nusd")
    prompt_excerpt: str | None
    active: bool = True


class CacheStats(ApiModel):
    entries_active: int
    entries_total: int
    hits_total: int
    tokens_saved: int
    avoided_cost_usd: float


class PurgeRequest(ApiModel):
    project_id: uuid.UUID | None = None


@router.get("/stats", response_model=CacheStats, summary="Cache totals")
async def stats(_: Viewer, session: SessionDep) -> CacheStats:
    now = datetime.now(UTC)
    active = CacheEntry.invalidated.is_(False) & (CacheEntry.expires_at > now)
    row = (
        await session.execute(
            select(
                func.count().filter(active),
                func.count(),
                func.coalesce(func.sum(CacheEntry.hits), 0),
                func.coalesce(func.sum(CacheEntry.tokens_saved), 0),
                func.coalesce(func.sum(CacheEntry.avoided_cost_nusd), 0),
            )
        )
    ).one()
    return CacheStats(
        entries_active=int(row[0]),
        entries_total=int(row[1]),
        hits_total=int(row[2]),
        tokens_saved=int(row[3]),
        avoided_cost_usd=nusd_to_usd(int(row[4])),
    )


@router.get("/entries", response_model=list[CacheEntryOut], summary="Most valuable cache entries")
async def entries(
    _: Viewer,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[CacheEntryOut]:
    now = datetime.now(UTC)
    stmt = (
        select(CacheEntry, Project.name)
        .outerjoin(Project, Project.id == CacheEntry.project_id)
        # Live entries first (they are the ones saving money now), then by value.
        .order_by(
            case((CacheEntry.invalidated.is_(False) & (CacheEntry.expires_at > now), 0), else_=1),
            CacheEntry.avoided_cost_nusd.desc(),
            CacheEntry.created_at.desc(),
        )
        .limit(limit)
    )
    if project_id:
        stmt = stmt.where(CacheEntry.project_id == project_id)
    return [
        CacheEntryOut.model_validate(e).model_copy(
            update={"project_name": name, "active": not e.invalidated and e.expires_at > now}
        )
        for e, name in (await session.execute(stmt)).all()
    ]


@router.delete("/entries/{key_hash}", response_model=Message, summary="Invalidate one entry")
async def invalidate(
    key_hash: str, actor: Admin, session: SessionDep, container: ContainerDep
) -> Message:
    entry = await session.get(CacheEntry, key_hash)
    if entry is None:
        raise NotFoundError("Cache entry not found")
    await ResponseCache(container.redis).invalidate([key_hash])
    await SemanticIndex(container.db.sessionmaker, 1.0).remove([key_hash])
    entry.invalidated = True
    audit(session, actor, "cache.invalidated", "cache_entry", key_hash)
    await session.commit()
    return Message(message="Entry invalidated")


@router.post("/purge", response_model=Message, summary="Invalidate all entries (or one project's)")
async def purge(
    body: PurgeRequest, actor: Admin, session: SessionDep, container: ContainerDep
) -> Message:
    now = datetime.now(UTC)
    stmt = select(CacheEntry.key_hash).where(
        CacheEntry.invalidated.is_(False), CacheEntry.expires_at > now
    )
    if body.project_id:
        stmt = stmt.where(CacheEntry.project_id == body.project_id)
    keys = list((await session.scalars(stmt)).all())
    removed = 0
    for i in range(0, len(keys), 500):
        batch = keys[i : i + 500]
        removed += await ResponseCache(container.redis).invalidate(batch)
        await SemanticIndex(container.db.sessionmaker, 1.0).remove(batch)
    if keys:
        await session.execute(
            update(CacheEntry).where(CacheEntry.key_hash.in_(keys)).values(invalidated=True)
        )
    audit(
        session,
        actor,
        "cache.purged",
        "project" if body.project_id else None,
        body.project_id,
        entries=len(keys),
    )
    await session.commit()
    return Message(message=f"Invalidated {len(keys)} entries")
