from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.core.errors import AppError, NotFoundError
from tokenshield.core.security import generate_api_key
from tokenshield.keys.models import ApiKey
from tokenshield.keys.schemas import KeyCreated, KeyIn, KeyOut, KeyUpdate
from tokenshield.projects.models import Project


def to_out(key: ApiKey, project_name: str | None = None) -> KeyOut:
    return KeyOut(
        id=key.id,
        project_id=key.project_id,
        project_name=project_name,
        name=key.name,
        prefix=key.prefix,
        display=f"tsk_{key.prefix}_****",
        rpm_limit=key.rpm_limit,
        tpm_limit=key.tpm_limit,
        concurrency_limit=key.concurrency_limit,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
    )


async def list_keys(
    session: AsyncSession, project_id: uuid.UUID | None, include_revoked: bool
) -> list[KeyOut]:
    stmt = (
        select(ApiKey, Project.name)
        .join(Project, Project.id == ApiKey.project_id)
        .order_by(ApiKey.created_at.desc())
    )
    if project_id:
        stmt = stmt.where(ApiKey.project_id == project_id)
    if not include_revoked:
        stmt = stmt.where(ApiKey.revoked_at.is_(None))
    return [to_out(k, name) for k, name in (await session.execute(stmt)).all()]


async def create_key(session: AsyncSession, data: KeyIn, pepper: str, actor: Actor) -> KeyCreated:
    project = await session.get(Project, data.project_id)
    if project is None or project.archived:
        raise AppError("Project does not exist or is archived", code="unknown_project")
    generated = generate_api_key(pepper)
    key = ApiKey(
        **data.model_dump(),
        prefix=generated.prefix,
        secret_hash=generated.secret_hash,
        created_by=actor.id,
    )
    session.add(key)
    await session.flush()
    await session.refresh(key)
    audit(session, actor, "api_key.created", "api_key", key.id, name=key.name, project=project.slug)
    await session.commit()
    return KeyCreated(**to_out(key, project.name).model_dump(), key=generated.plaintext)


async def update_key(
    session: AsyncSession, key_id: uuid.UUID, data: KeyUpdate, actor: Actor
) -> KeyOut:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise NotFoundError("API key not found")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(key, field, value)
    audit(
        session,
        actor,
        "api_key.updated",
        "api_key",
        key.id,
        **{k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return to_out(key)


async def revoke_key(session: AsyncSession, key_id: uuid.UUID, actor: Actor) -> KeyOut:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise NotFoundError("API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        audit(session, actor, "api_key.revoked", "api_key", key.id, name=key.name)
        await session.commit()
    return to_out(key)
