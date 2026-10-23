"""Health, readiness, metrics and deployment info."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text

from tokenshield import __version__
from tokenshield.auth.dependencies import Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.core.schemas import ApiModel
from tokenshield.keys.models import ApiKey
from tokenshield.projects.models import Project
from tokenshield.providers.models import Model

router = APIRouter(tags=["system"])


@router.get("/healthz", summary="Liveness")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _probe(name: str, coro: Any) -> tuple[str, dict[str, Any]]:
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2)
        return name, {"ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return name, {"ok": False, "error": type(exc).__name__}


@router.get("/readyz", summary="Readiness: Postgres and Redis reachable")
async def readyz(container: ContainerDep, response: Response) -> dict[str, Any]:
    async def pg() -> None:
        async with container.db.engine.connect() as conn:
            await conn.execute(text("select 1"))

    checks = dict(
        await asyncio.gather(_probe("postgres", pg()), _probe("redis", container.redis.ping()))
    )
    ok = all(c["ok"] for c in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class SystemInfo(ApiModel):
    version: str
    environment: str
    cloud: str
    key_mode: str
    storage: str
    budget_failure_mode: str
    semantic_cache: bool
    store_content: bool
    projects: int
    models: int
    active_keys: int
    checks: dict[str, Any]


@router.get("/api/v1/system", response_model=SystemInfo, summary="Deployment configuration")
async def system(_: Viewer, session: SessionDep, container: ContainerDep) -> SystemInfo:
    s = container.settings
    projects = await session.scalar(select(func.count()).where(Project.archived.is_(False)))
    models = await session.scalar(select(func.count()).select_from(Model))
    keys = await session.scalar(select(func.count()).where(ApiKey.revoked_at.is_(None)))
    checks = dict([await _probe("redis", container.redis.ping())])
    checks["postgres"] = {"ok": True}
    return SystemInfo(
        version=__version__,
        environment=s.environment,
        cloud=s.cloud,
        key_mode=s.key_mode,
        storage=s.storage,
        budget_failure_mode=s.budget_failure_mode,
        semantic_cache=s.semantic_cache,
        store_content=s.store_content,
        projects=int(projects or 0),
        models=int(models or 0),
        active_keys=int(keys or 0),
        checks=checks,
    )
