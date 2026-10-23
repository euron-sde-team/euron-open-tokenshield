"""Providers, models and their price history."""

from __future__ import annotations

import time
import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.core.errors import AppError, ConflictError, NotFoundError
from tokenshield.core.sealing import KeySealer
from tokenshield.pricing.models import ModelPrice
from tokenshield.providers.models import Model, Provider
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


def _hint(api_key: str) -> str:
    return f"...{api_key[-4:]}" if len(api_key) >= 8 else "set"


def provider_out(p: Provider, model_count: int = 0) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        kind=p.kind,
        base_url=p.base_url,
        has_key=p.sealed_key is not None,
        key_hint=p.key_hint,
        timeout_s=float(p.timeout_s) if p.timeout_s is not None else None,
        enabled=p.enabled,
        created_at=p.created_at,
        model_count=model_count,
    )


async def list_providers(session: AsyncSession) -> list[ProviderOut]:
    counts = (
        select(Model.provider_id, func.count().label("n")).group_by(Model.provider_id).subquery()
    )
    rows = (
        await session.execute(
            select(Provider, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.provider_id == Provider.id)
            .order_by(Provider.name)
        )
    ).all()
    return [provider_out(p, n) for p, n in rows]


async def _seal(sealer: KeySealer, provider: Provider, api_key: str | None) -> None:
    if api_key:
        provider.sealed_key = await sealer.seal(api_key, f"provider:{provider.id}")
        provider.key_hint = _hint(api_key)
    else:
        provider.sealed_key = None
        provider.key_hint = None


async def create_provider(
    session: AsyncSession, data: ProviderIn, sealer: KeySealer, actor: Actor
) -> ProviderOut:
    if await session.scalar(select(Provider.id).where(Provider.name == data.name)):
        raise ConflictError("A provider with this name exists", code="name_taken")
    provider = Provider(
        id=uuid.uuid4(),
        name=data.name,
        kind=data.kind,
        base_url=str(data.base_url).rstrip("/"),
        timeout_s=data.timeout_s,
        enabled=data.enabled,
    )
    await _seal(sealer, provider, data.api_key)
    session.add(provider)
    await session.flush()
    await session.refresh(provider)
    audit(
        session,
        actor,
        "provider.created",
        "provider",
        provider.id,
        name=provider.name,
        kind=provider.kind,
    )
    await session.commit()
    return provider_out(provider)


async def update_provider(
    session: AsyncSession,
    provider_id: uuid.UUID,
    data: ProviderUpdate,
    sealer: KeySealer,
    actor: Actor,
) -> ProviderOut:
    provider = await session.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found")
    changes = data.model_dump(exclude_unset=True)
    if "api_key" in changes:
        await _seal(sealer, provider, changes.pop("api_key"))
        audit(session, actor, "provider.key_rotated", "provider", provider.id)
    if "base_url" in changes and changes["base_url"] is not None:
        changes["base_url"] = str(changes["base_url"]).rstrip("/")
    for field, value in changes.items():
        setattr(provider, field, value)
    if changes:
        audit(
            session,
            actor,
            "provider.updated",
            "provider",
            provider.id,
            **{k: str(v) for k, v in changes.items()},
        )
    await session.commit()
    return provider_out(provider)


async def check_provider(
    session: AsyncSession, provider_id: uuid.UUID, sealer: KeySealer, client: httpx.AsyncClient
) -> ProviderTest:
    """Reachability and credential check against the provider's model listing."""
    provider = await session.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found")
    headers: dict[str, str] = {}
    key = (
        await sealer.open(provider.sealed_key, f"provider:{provider.id}")
        if provider.sealed_key
        else None
    )
    base = provider.base_url.rstrip("/")
    if provider.kind == "anthropic":
        url = base + ("/models" if base.endswith("/v1") else "/v1/models")
        headers["anthropic-version"] = "2023-06-01"
        if key:
            headers["x-api-key"] = key
    else:
        url = base + "/models"
        if key:
            headers["authorization"] = f"Bearer {key}"
    t0 = time.perf_counter()
    try:
        resp = await client.get(url, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        return ProviderTest(
            ok=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            message=f"Unreachable: {type(exc).__name__}",
        )
    ms = int((time.perf_counter() - t0) * 1000)
    if resp.status_code in (401, 403):
        return ProviderTest(
            ok=False, latency_ms=ms, message="Reached the provider, but the API key was rejected"
        )
    if resp.status_code >= 400:
        return ProviderTest(
            ok=False, latency_ms=ms, message=f"Provider answered {resp.status_code}"
        )
    return ProviderTest(ok=True, latency_ms=ms, message="Connected")


async def _latest_prices(
    session: AsyncSession, model_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ModelPrice]:
    if not model_ids:
        return {}
    rows = await session.scalars(
        select(ModelPrice)
        .where(ModelPrice.model_id.in_(model_ids))
        .ext(distinct_on(ModelPrice.model_id))
        .order_by(ModelPrice.model_id, ModelPrice.version.desc())
    )
    return {p.model_id: p for p in rows.all()}


def _model_out(m: Model, p: Provider, price: ModelPrice | None) -> ModelOut:
    return ModelOut(
        id=m.id,
        alias=m.alias,
        provider_id=p.id,
        provider_name=p.name,
        provider_kind=p.kind,
        upstream_model=m.upstream_model,
        kind=m.kind,
        tokenizer=m.tokenizer,
        context_window=m.context_window,
        max_output_tokens=m.max_output_tokens,
        restricted=m.restricted,
        enabled=m.enabled,
        price=PriceOut.model_validate(price) if price else None,
        created_at=m.created_at,
    )


async def list_models(session: AsyncSession) -> list[ModelOut]:
    rows = (
        await session.execute(
            select(Model, Provider)
            .join(Provider, Provider.id == Model.provider_id)
            .order_by(Model.alias)
        )
    ).all()
    prices = await _latest_prices(session, [m.id for m, _ in rows])
    return [_model_out(m, p, prices.get(m.id)) for m, p in rows]


async def get_model(session: AsyncSession, model_id: uuid.UUID) -> ModelOut:
    row = (
        await session.execute(
            select(Model, Provider)
            .join(Provider, Provider.id == Model.provider_id)
            .where(Model.id == model_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Model not found")
    prices = await _latest_prices(session, [model_id])
    return _model_out(row[0], row[1], prices.get(model_id))


async def create_model(session: AsyncSession, data: ModelIn, actor: Actor) -> ModelOut:
    if await session.scalar(select(Model.id).where(Model.alias == data.alias)):
        raise ConflictError("A model with this alias exists", code="alias_taken")
    if not await session.get(Provider, data.provider_id):
        raise AppError("Provider does not exist", code="unknown_provider")
    model = Model(**data.model_dump(exclude={"price"}))
    session.add(model)
    await session.flush()
    if data.price:
        session.add(
            ModelPrice(model_id=model.id, version=1, created_by=actor.id, **data.price.model_dump())
        )
    audit(session, actor, "model.created", "model", model.id, alias=model.alias)
    await session.commit()
    return await get_model(session, model.id)


async def update_model(
    session: AsyncSession, model_id: uuid.UUID, data: ModelUpdate, actor: Actor
) -> ModelOut:
    model = await session.get(Model, model_id)
    if model is None:
        raise NotFoundError("Model not found")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(model, field, value)
    audit(
        session,
        actor,
        "model.updated",
        "model",
        model.id,
        **{k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return await get_model(session, model_id)


async def add_price(
    session: AsyncSession, model_id: uuid.UUID, data: PriceIn, actor: Actor
) -> PriceOut:
    """Prices are immutable versions: usage rows keep pointing at the price they used."""
    model = await session.get(Model, model_id, with_for_update=True)
    if model is None:
        raise NotFoundError("Model not found")
    current = await session.scalar(
        select(func.max(ModelPrice.version)).where(ModelPrice.model_id == model_id)
    )
    price = ModelPrice(
        model_id=model_id, version=int(current or 0) + 1, created_by=actor.id, **data.model_dump()
    )
    session.add(price)
    await session.flush()
    await session.refresh(price)
    audit(
        session,
        actor,
        "model.price_added",
        "model",
        model_id,
        version=price.version,
        input_per_m=str(price.input_per_m),
        output_per_m=str(price.output_per_m),
    )
    await session.commit()
    return PriceOut.model_validate(price)


async def price_history(session: AsyncSession, model_id: uuid.UUID) -> list[PriceOut]:
    rows = await session.scalars(
        select(ModelPrice)
        .where(ModelPrice.model_id == model_id)
        .order_by(ModelPrice.version.desc())
    )
    return [PriceOut.model_validate(p) for p in rows.all()]
