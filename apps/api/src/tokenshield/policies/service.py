from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tokenshield.audit.service import Actor, audit
from tokenshield.core.errors import AppError, NotFoundError
from tokenshield.policies.models import PolicyRule
from tokenshield.policies.schemas import RuleIn, RuleUpdate, validate_params


async def list_rules(session: AsyncSession) -> Sequence[PolicyRule]:
    return (await session.scalars(select(PolicyRule).order_by(PolicyRule.created_at))).all()


async def create_rule(session: AsyncSession, data: RuleIn, actor: Actor) -> PolicyRule:
    rule = PolicyRule(**data.model_dump())
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    audit(session, actor, "policy.created", "policy", rule.id, name=rule.name, kind=rule.kind)
    await session.commit()
    return rule


async def update_rule(
    session: AsyncSession, rule_id: uuid.UUID, data: RuleUpdate, actor: Actor
) -> PolicyRule:
    rule = await session.get(PolicyRule, rule_id)
    if rule is None:
        raise NotFoundError("Policy not found")
    changes = data.model_dump(exclude_unset=True)
    params = changes.get("params", rule.params)
    action = changes.get("action", rule.action)
    try:
        changes["params"] = validate_params(rule.kind, params, action)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_policy") from None
    for field, value in changes.items():
        setattr(rule, field, value)
    audit(
        session,
        actor,
        "policy.updated",
        "policy",
        rule.id,
        **{k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return rule


async def delete_rule(session: AsyncSession, rule_id: uuid.UUID, actor: Actor) -> None:
    rule = await session.get(PolicyRule, rule_id)
    if rule is None:
        raise NotFoundError("Policy not found")
    audit(session, actor, "policy.deleted", "policy", rule.id, name=rule.name)
    await session.delete(rule)
    await session.commit()
