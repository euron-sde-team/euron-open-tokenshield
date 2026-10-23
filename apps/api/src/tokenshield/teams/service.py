from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.core.errors import ConflictError, NotFoundError
from tokenshield.core.text import slugify
from tokenshield.projects.models import Project
from tokenshield.teams.models import Team
from tokenshield.teams.schemas import TeamIn, TeamOut, TeamUpdate


async def list_teams(session: AsyncSession) -> list[TeamOut]:
    counts = (
        select(Project.team_id, func.count().label("n"))
        .where(Project.archived.is_(False))
        .group_by(Project.team_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Team, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.team_id == Team.id)
            .order_by(Team.name)
        )
    ).all()
    return [TeamOut.model_validate(t).model_copy(update={"project_count": n}) for t, n in rows]


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug, i = base, 2
    while await session.scalar(select(Team.id).where(Team.slug == slug)):
        slug, i = f"{base}-{i}", i + 1
    return slug


async def create_team(session: AsyncSession, data: TeamIn, actor: Actor) -> TeamOut:
    team = Team(
        name=data.name, description=data.description, slug=await _unique_slug(session, data.name)
    )
    session.add(team)
    await session.flush()
    audit(session, actor, "team.created", "team", team.id, name=team.name)
    await session.commit()
    return TeamOut.model_validate(team)


async def update_team(
    session: AsyncSession, team_id: uuid.UUID, data: TeamUpdate, actor: Actor
) -> TeamOut:
    team = await session.get(Team, team_id)
    if team is None:
        raise NotFoundError("Team not found")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(team, field, value)
    audit(session, actor, "team.updated", "team", team.id, **changes)
    await session.commit()
    return TeamOut.model_validate(team)


async def delete_team(session: AsyncSession, team_id: uuid.UUID, actor: Actor) -> None:
    team = await session.get(Team, team_id)
    if team is None:
        raise NotFoundError("Team not found")
    in_use = await session.scalar(
        select(func.count()).where(Project.team_id == team_id, Project.archived.is_(False))
    )
    if in_use:
        raise ConflictError(
            "Move or archive this team's projects before deleting it", code="team_in_use"
        )
    audit(session, actor, "team.deleted", "team", team.id, name=team.name)
    await session.delete(team)
    await session.commit()
