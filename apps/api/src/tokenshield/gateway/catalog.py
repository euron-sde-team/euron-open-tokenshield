"""The gateway's read model: everything a request needs, loaded in a handful of queries
and cached in-process (see ``core.cache.ConfigCache``).

A request should never wait on Postgres for configuration. The snapshot is rebuilt at most
every few seconds per instance, or immediately after an admin write bumps the version.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.budgets.models import Budget
from tokenshield.core.sealing import KeySealer
from tokenshield.keys.models import ApiKey
from tokenshield.policies.models import PolicyRule
from tokenshield.pricing.engine import Price
from tokenshield.pricing.models import ModelPrice
from tokenshield.projects.models import Project
from tokenshield.providers.models import Model, Provider


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: uuid.UUID
    alias: str
    kind: str
    provider_id: uuid.UUID
    provider_name: str
    provider_kind: str
    base_url: str
    timeout_s: float | None
    upstream_model: str
    tokenizer: str
    context_window: int
    max_output_tokens: int
    restricted: bool
    price: Price | None


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    id: uuid.UUID
    team_id: uuid.UUID | None
    slug: str
    name: str
    cache_enabled: bool
    cache_ttl_s: int
    cache_nondeterministic: bool
    semantic_cache_enabled: bool
    allowed_models: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class BudgetInfo:
    id: uuid.UUID
    name: str
    scope_type: str
    scope_id: str | None
    period: str
    limit_nusd: int
    mode: str
    alert_threshold_pct: int


@dataclass(frozen=True, slots=True)
class RuleInfo:
    id: uuid.UUID
    name: str
    kind: str
    scope_type: str
    scope_id: str | None
    params: dict[str, Any]
    action: str


@dataclass(frozen=True, slots=True)
class KeyInfo:
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    secret_hash: str
    rpm_limit: int | None
    tpm_limit: int | None
    concurrency_limit: int | None
    expires_at: datetime | None
    revoked: bool


@dataclass(frozen=True, slots=True)
class Catalog:
    models: dict[str, ModelInfo]
    projects: dict[uuid.UUID, ProjectInfo]
    budgets: tuple[BudgetInfo, ...]
    rules: tuple[RuleInfo, ...]
    provider_keys: dict[uuid.UUID, str | None] = field(default_factory=dict)


# Decrypted provider credentials, keyed by a digest of the sealed blob. KMS is only called
# when a credential actually changes, not on every catalog refresh.
_opened: dict[tuple[uuid.UUID, str], str] = {}


async def _open_key(sealer: KeySealer, provider: Provider) -> str | None:
    if not provider.sealed_key:
        return None
    digest = hashlib.sha256(provider.sealed_key).hexdigest()
    cache_key = (provider.id, digest)
    if cache_key not in _opened:
        _opened[cache_key] = await sealer.open(provider.sealed_key, f"provider:{provider.id}")
    return _opened[cache_key]


async def load_catalog(session: AsyncSession, sealer: KeySealer) -> Catalog:
    rows = (
        await session.execute(
            select(Model, Provider)
            .join(Provider, Provider.id == Model.provider_id)
            .where(Model.enabled.is_(True), Provider.enabled.is_(True))
        )
    ).all()

    # Latest price version per model in one query (DISTINCT ON).
    prices: dict[uuid.UUID, ModelPrice] = {
        p.model_id: p
        for p in (
            await session.scalars(
                select(ModelPrice)
                .distinct(ModelPrice.model_id)
                .order_by(ModelPrice.model_id, ModelPrice.version.desc())
            )
        ).all()
    }

    models: dict[str, ModelInfo] = {}
    provider_keys: dict[uuid.UUID, str | None] = {}
    for model, provider in rows:
        if provider.id not in provider_keys:
            provider_keys[provider.id] = await _open_key(sealer, provider)
        price_row = prices.get(model.id)
        price = (
            Price(
                id=price_row.id,
                version=price_row.version,
                input_per_m=Decimal(price_row.input_per_m),
                cached_input_per_m=(
                    Decimal(price_row.cached_input_per_m)
                    if price_row.cached_input_per_m is not None
                    else None
                ),
                output_per_m=Decimal(price_row.output_per_m),
            )
            if price_row
            else None
        )
        models[model.alias] = ModelInfo(
            id=model.id,
            alias=model.alias,
            kind=model.kind,
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            base_url=provider.base_url,
            timeout_s=float(provider.timeout_s) if provider.timeout_s is not None else None,
            upstream_model=model.upstream_model,
            tokenizer=model.tokenizer,
            context_window=model.context_window,
            max_output_tokens=model.max_output_tokens,
            restricted=model.restricted,
            price=price,
        )

    projects = {
        p.id: ProjectInfo(
            id=p.id,
            team_id=p.team_id,
            slug=p.slug,
            name=p.name,
            cache_enabled=p.cache_enabled,
            cache_ttl_s=p.cache_ttl_s,
            cache_nondeterministic=p.cache_nondeterministic,
            semantic_cache_enabled=p.semantic_cache_enabled,
            allowed_models=tuple(p.allowed_models) if p.allowed_models is not None else None,
        )
        for p in (await session.scalars(select(Project).where(Project.archived.is_(False)))).all()
    }

    budgets = tuple(
        BudgetInfo(
            id=b.id,
            name=b.name,
            scope_type=b.scope_type,
            scope_id=b.scope_id,
            period=b.period,
            limit_nusd=b.limit_nusd,
            mode=b.mode,
            alert_threshold_pct=b.alert_threshold_pct,
        )
        for b in (await session.scalars(select(Budget).where(Budget.enabled.is_(True)))).all()
    )

    rules = tuple(
        RuleInfo(
            id=r.id,
            name=r.name,
            kind=r.kind,
            scope_type=r.scope_type,
            scope_id=r.scope_id,
            params=dict(r.params or {}),
            action=r.action,
        )
        for r in (
            await session.scalars(select(PolicyRule).where(PolicyRule.enabled.is_(True)))
        ).all()
    )
    return Catalog(models, projects, budgets, rules, provider_keys)


async def load_key(session: AsyncSession, prefix: str) -> KeyInfo | None:
    key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if key is None:
        return None
    return KeyInfo(
        id=key.id,
        project_id=key.project_id,
        name=key.name,
        secret_hash=key.secret_hash,
        rpm_limit=key.rpm_limit,
        tpm_limit=key.tpm_limit,
        concurrency_limit=key.concurrency_limit,
        expires_at=key.expires_at,
        revoked=key.revoked_at is not None,
    )
