from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.core.errors import AppError, NotFoundError
from tokenshield.core.text import slugify
from tokenshield.keys.models import ApiKey
from tokenshield.projects.models import Project
from tokenshield.projects.schemas import ProjectIn, ProjectOut, ProjectUpdate
from tokenshield.providers.models import Model
from tokenshield.teams.models import Team


async def list_projects(session: AsyncSession, include_archived: bool = False) -> list[ProjectOut]:
    keys = (
        select(ApiKey.project_id, func.count().label("n"))
        .where(ApiKey.revoked_at.is_(None))
        .group_by(ApiKey.project_id)
        .subquery()
    )
    stmt = (
        select(Project, Team.name, func.coalesce(keys.c.n, 0))
        .outerjoin(Team, Team.id == Project.team_id)
        .outerjoin(keys, keys.c.project_id == Project.id)
        .order_by(Project.name)
    )
    if not include_archived:
        stmt = stmt.where(Project.archived.is_(False))
    rows = (await session.execute(stmt)).all()
    return [
        ProjectOut.model_validate(p).model_copy(update={"team_name": team, "key_count": n})
        for p, team, n in rows
    ]


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


async def _validate(
    session: AsyncSession, team_id: uuid.UUID | None, models: list[str] | None
) -> None:
    if team_id and not await session.get(Team, team_id):
        raise AppError("Team does not exist", code="unknown_team")
    if models:
        known = set(
            (await session.scalars(select(Model.alias).where(Model.alias.in_(models)))).all()
        )
        if missing := sorted(set(models) - known):
            raise AppError(f"Unknown model aliases: {', '.join(missing)}", code="unknown_models")


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug, i = base, 2
    while await session.scalar(select(Project.id).where(Project.slug == slug)):
        slug, i = f"{base}-{i}", i + 1
    return slug


async def create_project(session: AsyncSession, data: ProjectIn, actor: Actor) -> ProjectOut:
    await _validate(session, data.team_id, data.allowed_models)
    project = Project(**data.model_dump(), slug=await _unique_slug(session, data.name))
    session.add(project)
    await session.flush()
    audit(session, actor, "project.created", "project", project.id, name=project.name)
    await session.commit()
    return ProjectOut.model_validate(project)


async def update_project(
    session: AsyncSession, project_id: uuid.UUID, data: ProjectUpdate, actor: Actor
) -> ProjectOut:
    project = await get_project(session, project_id)
    changes = data.model_dump(exclude_unset=True)
    await _validate(session, changes.get("team_id"), changes.get("allowed_models"))
    for field, value in changes.items():
        setattr(project, field, value)
    audit(
        session,
        actor,
        "project.updated",
        "project",
        project.id,
        **{k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return ProjectOut.model_validate(project)
