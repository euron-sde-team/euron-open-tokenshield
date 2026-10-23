"""OpenAI-compatible gateway endpoints. Point any OpenAI SDK at ``<host>/v1``."""

from __future__ import annotations

from typing import Annotated, Any

import orjson
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from tokenshield.core.deps import ContainerDep
from tokenshield.core.errors import AppError
from tokenshield.gateway.catalog import Catalog
from tokenshield.gateway.context import RequestContext
from tokenshield.gateway.dependencies import authenticate_key, get_catalog
from tokenshield.gateway.service import GatewayService

router = APIRouter(prefix="/v1", tags=["gateway"])

MAX_BODY_BYTES = 8 * 1024 * 1024


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise AppError("Request body too large", code="body_too_large")
    try:
        data = orjson.loads(raw)
    except orjson.JSONDecodeError:
        raise AppError("Request body must be JSON", code="invalid_json") from None
    if not isinstance(data, dict):
        raise AppError("Request body must be a JSON object", code="invalid_json")
    return data


CtxDep = Annotated[RequestContext, Depends(authenticate_key)]
CatalogDep = Annotated[Catalog, Depends(get_catalog)]


@router.post(
    "/chat/completions",
    summary="Create a chat completion (OpenAI-compatible)",
    response_description="An OpenAI chat.completion object, or an SSE stream when stream=true",
)
async def chat_completions(
    request: Request, ctx: CtxDep, container: ContainerDep, catalog: CatalogDep
) -> Response:
    body = await _json_body(request)
    if not ctx.end_user and isinstance(body.get("user"), str):
        ctx.end_user = body["user"][:200]
    return await GatewayService(container, catalog).chat(ctx, body)


@router.post("/embeddings", summary="Create embeddings (OpenAI-compatible)")
async def embeddings(
    request: Request, ctx: CtxDep, container: ContainerDep, catalog: CatalogDep
) -> Response:
    body = await _json_body(request)
    return await GatewayService(container, catalog).embeddings(ctx, body)


@router.get("/models", summary="List models available to this key")
async def list_models(ctx: CtxDep, catalog: CatalogDep) -> dict[str, Any]:
    allowed = ctx.project.allowed_models
    data = [
        {
            "id": m.alias,
            "object": "model",
            "created": 0,
            "owned_by": m.provider_name,
            "tokenshield": {
                "kind": m.kind,
                "context_window": m.context_window,
                "priced": m.price is not None,
                "restricted": m.restricted,
            },
        }
        for m in sorted(catalog.models.values(), key=lambda m: m.alias)
        if allowed is None or m.alias in allowed
    ]
    return {"object": "list", "data": data}
