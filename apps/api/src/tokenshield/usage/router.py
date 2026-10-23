from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import Response

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.core.schemas import Page
from tokenshield.usage import service
from tokenshield.usage.analytics import Analytics
from tokenshield.usage.schemas import (
    BreakdownRow,
    Dimension,
    ExportDownload,
    ExportIn,
    ExportOut,
    Overview,
    Range,
    SeriesPoint,
    TaskSummary,
    UsageEventDetail,
    UsageEventOut,
)

router = APIRouter(prefix="/api/v1", tags=["usage and analytics"])


@router.get("/usage/events", response_model=Page[UsageEventOut], summary="Request log")
async def list_events(
    _: Viewer,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    project_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    model: str | None = None,
    status: str | None = None,
    cache_status: str | None = None,
    end_user: str | None = None,
    task_id: str | None = None,
    q: str | None = Query(None, max_length=64, description="Request id prefix"),
) -> Page[UsageEventOut]:
    return await service.list_events(
        session,
        cursor=cursor,
        limit=limit,
        project_id=project_id,
        api_key_id=api_key_id,
        model=model,
        status=status,
        cache_status=cache_status,
        end_user=end_user,
        task_id=task_id,
        q=q,
    )


@router.get(
    "/usage/events/{request_id}",
    response_model=UsageEventDetail,
    summary="One request with its budget reservations and reconciliations",
)
async def get_event(request_id: str, _: Viewer, session: SessionDep) -> UsageEventDetail:
    return await service.get_event(session, request_id)


@router.get("/analytics/overview", response_model=Overview, summary="Totals vs previous period")
async def overview(
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    period: Range = Query("24h", alias="range"),
    project_id: uuid.UUID | None = None,
) -> Overview:
    return await Analytics(session, container.redis).overview(period, project_id)


@router.get("/analytics/timeseries", response_model=list[SeriesPoint], summary="Spend over time")
async def timeseries(
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    period: Range = Query("24h", alias="range"),
    project_id: uuid.UUID | None = None,
) -> list[SeriesPoint]:
    return await Analytics(session, container.redis).timeseries(period, project_id)


@router.get("/analytics/breakdown", response_model=list[BreakdownRow], summary="Spend by dimension")
async def breakdown(
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    by: Dimension = "model",
    period: Range = Query("24h", alias="range"),
    project_id: uuid.UUID | None = None,
) -> list[BreakdownRow]:
    return await Analytics(session, container.redis).breakdown(period, by, project_id)


@router.get("/analytics/tasks", response_model=list[TaskSummary], summary="Agent tasks")
async def tasks(
    _: Viewer,
    session: SessionDep,
    container: ContainerDep,
    period: Range = Query("24h", alias="range"),
    project_id: uuid.UUID | None = None,
) -> list[TaskSummary]:
    return await Analytics(session, container.redis).tasks(period, project_id)


@router.get("/exports", response_model=list[ExportOut], summary="Recent report exports")
async def list_exports(_: Viewer, session: SessionDep) -> list[ExportOut]:
    return await service.list_exports(session)


@router.post("/exports", response_model=ExportOut, status_code=201, summary="Export usage as CSV")
async def create_export(
    body: ExportIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ExportOut:
    return await service.create_export(session, body, container.storage, actor)


@router.get(
    "/exports/{export_id}/download",
    response_model=ExportDownload,
    summary="Get a download link for an export",
)
async def export_link(
    export_id: uuid.UUID, _: Viewer, session: SessionDep, container: ContainerDep
) -> ExportDownload:
    link, _export = await service.export_download(session, export_id, container.storage)
    if link.url is None:
        link.url = f"/api/v1/exports/{export_id}/file"
    return link


@router.get("/exports/{export_id}/file", summary="Stream an export through the API")
async def export_file(
    export_id: uuid.UUID, _: Viewer, session: SessionDep, container: ContainerDep
) -> Response:
    link, export = await service.export_download(session, export_id, container.storage)
    data = await container.storage.get(export.object_key)
    return Response(
        data,
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{link.filename}"'},
    )
