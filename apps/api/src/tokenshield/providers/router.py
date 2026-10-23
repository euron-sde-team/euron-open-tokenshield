from __future__ import annotations

import uuid

from fastapi import APIRouter

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.providers import service
from tokenshield.providers.schemas import (
    ModelIn,
    ModelOut,
    ModelUpdate,
    PriceIn,
    PriceOut,
    ProviderIn,
    ProviderOut,
    ProviderTest,
    ProviderUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["providers and models"])


@router.get("/providers", response_model=list[ProviderOut], summary="List providers")
async def list_providers(_: Viewer, session: SessionDep) -> list[ProviderOut]:
    return await service.list_providers(session)


@router.post("/providers", response_model=ProviderOut, status_code=201, summary="Add a provider")
async def create_provider(
    body: ProviderIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ProviderOut:
    out = await service.create_provider(session, body, container.sealer, actor)
    await container.config_cache.invalidate()
    return out


@router.patch("/providers/{provider_id}", response_model=ProviderOut, summary="Update a provider")
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ProviderOut:
    out = await service.update_provider(session, provider_id, body, container.sealer, actor)
    await container.config_cache.invalidate()
    return out


@router.post(
    "/providers/{provider_id}/test", response_model=ProviderTest, summary="Test connectivity"
)
async def check_provider(
    provider_id: uuid.UUID, _: Admin, session: SessionDep, container: ContainerDep
) -> ProviderTest:
    return await service.check_provider(session, provider_id, container.sealer, container.http)


@router.get("/models", response_model=list[ModelOut], summary="List models with current prices")
async def list_models(_: Viewer, session: SessionDep) -> list[ModelOut]:
    return await service.list_models(session)


@router.post("/models", response_model=ModelOut, status_code=201, summary="Add a model alias")
async def create_model(
    body: ModelIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ModelOut:
    out = await service.create_model(session, body, actor)
    await container.config_cache.invalidate()
    return out


@router.patch("/models/{model_id}", response_model=ModelOut, summary="Update a model")
async def update_model(
    model_id: uuid.UUID,
    body: ModelUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ModelOut:
    out = await service.update_model(session, model_id, body, actor)
    await container.config_cache.invalidate()
    return out


@router.get("/models/{model_id}/prices", response_model=list[PriceOut], summary="Price history")
async def price_history(model_id: uuid.UUID, _: Viewer, session: SessionDep) -> list[PriceOut]:
    return await service.price_history(session, model_id)


@router.post(
    "/models/{model_id}/prices",
    response_model=PriceOut,
    status_code=201,
    summary="Publish a new price version",
)
async def add_price(
    model_id: uuid.UUID, body: PriceIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> PriceOut:
    out = await service.add_price(session, model_id, body, actor)
    await container.config_cache.invalidate()
    return out
