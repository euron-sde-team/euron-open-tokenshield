from __future__ import annotations

import uuid

from fastapi import APIRouter

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.projects import service
from tokenshield.projects.schemas import ProjectIn, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut], summary="List projects")
async def list_projects(
    _: Viewer, session: SessionDep, include_archived: bool = False
) -> list[ProjectOut]:
    return await service.list_projects(session, include_archived)


@router.get("/{project_id}", response_model=ProjectOut, summary="Get a project")
async def get_project(project_id: uuid.UUID, _: Viewer, session: SessionDep) -> ProjectOut:
    return ProjectOut.model_validate(await service.get_project(session, project_id))


@router.post("", response_model=ProjectOut, status_code=201, summary="Create a project")
async def create_project(
    body: ProjectIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ProjectOut:
    out = await service.create_project(session, body, actor)
    await container.config_cache.invalidate()
    return out


@router.patch("/{project_id}", response_model=ProjectOut, summary="Update or archive a project")
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ProjectOut:
    out = await service.update_project(session, project_id, body, actor)
    await container.config_cache.invalidate()
    return out
