"""Send a request through the full gateway pipeline from the dashboard.

Runs as the chosen project with no API key: budgets, policies, caching and accounting all
apply, and the request appears in the log with source "playground".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import Field

from tokenshield.auth.dependencies import Admin
from tokenshield.core.deps import ContainerDep
from tokenshield.core.errors import NotFoundError
from tokenshield.core.schemas import ApiModel
from tokenshield.gateway.catalog import Catalog
from tokenshield.gateway.context import RequestContext
from tokenshield.gateway.dependencies import get_catalog
from tokenshield.gateway.service import GatewayService, new_request_id

router = APIRouter(prefix="/api/v1/playground", tags=["playground"])


class PlaygroundMessage(ApiModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=200_000)


class PlaygroundRequest(ApiModel):
    project_id: uuid.UUID
    model: str
    messages: list[PlaygroundMessage] = Field(min_length=1, max_length=100)
    temperature: float | None = Field(0, ge=0, le=2)
    max_tokens: int | None = Field(None, ge=1, le=1_000_000)
    end_user: str | None = Field(None, max_length=200)
    task_id: str | None = Field(None, max_length=200)
    cache: Literal["on", "off"] = "on"


@router.post("/chat", summary="Run a chat completion through the gateway")
async def chat(
    body: PlaygroundRequest,
    _: Admin,
    container: ContainerDep,
    catalog: Annotated[Catalog, Depends(get_catalog)],
) -> Response:
    project = catalog.projects.get(body.project_id)
    if project is None:
        raise NotFoundError("Project not found or archived")
    payload: dict[str, Any] = {
        "model": body.model,
        "messages": [m.model_dump() for m in body.messages],
        "temperature": body.temperature,
    }
    if body.max_tokens:
        payload["max_tokens"] = body.max_tokens
    ctx = RequestContext(
        request_id=new_request_id(),
        project=project,
        key=None,
        source="playground",
        end_user=body.end_user,
        task_id=body.task_id,
        cache_header="off" if body.cache == "off" else None,
    )
    return await GatewayService(container, catalog).chat(ctx, payload)
