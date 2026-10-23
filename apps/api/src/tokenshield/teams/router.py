from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.teams import service
from tokenshield.teams.schemas import TeamIn, TeamOut, TeamUpdate

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("", response_model=list[TeamOut], summary="List teams")
async def list_teams(_: Viewer, session: SessionDep) -> list[TeamOut]:
    return await service.list_teams(session)


@router.post("", response_model=TeamOut, status_code=201, summary="Create a team")
async def create_team(body: TeamIn, actor: Admin, session: SessionDep) -> TeamOut:
    return await service.create_team(session, body, actor)


@router.patch("/{team_id}", response_model=TeamOut, summary="Update a team")
async def update_team(
    team_id: uuid.UUID, body: TeamUpdate, actor: Admin, session: SessionDep
) -> TeamOut:
    return await service.update_team(session, team_id, body, actor)


@router.delete("/{team_id}", status_code=204, summary="Delete an empty team")
async def delete_team(
    team_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Response:
    await service.delete_team(session, team_id, actor)
    await container.config_cache.invalidate()
    return Response(status_code=204)
