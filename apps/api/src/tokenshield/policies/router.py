from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Response

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.core.deps import ContainerDep, SessionDep
from tokenshield.policies import service
from tokenshield.policies.models import PolicyRule
from tokenshield.policies.schemas import RuleIn, RuleOut, RuleUpdate

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


@router.get("", response_model=list[RuleOut], summary="List waste-prevention policies")
async def list_rules(_: Viewer, session: SessionDep) -> Sequence[PolicyRule]:
    return await service.list_rules(session)


@router.post("", response_model=RuleOut, status_code=201, summary="Create a policy")
async def create_rule(
    body: RuleIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> PolicyRule:
    rule = await service.create_rule(session, body, actor)
    await container.config_cache.invalidate()
    return rule


@router.patch("/{rule_id}", response_model=RuleOut, summary="Update a policy")
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> PolicyRule:
    rule = await service.update_rule(session, rule_id, body, actor)
    await container.config_cache.invalidate()
    return rule


@router.delete("/{rule_id}", status_code=204, summary="Delete a policy")
async def delete_rule(
    rule_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Response:
    await service.delete_rule(session, rule_id, actor)
    await container.config_cache.invalidate()
    return Response(status_code=204)
