from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from tokenshield.auth.dependencies import Admin, Viewer
from tokenshield.budgets import service
from tokenshield.budgets.schemas import BudgetIn, BudgetOut, BudgetUpdate
from tokenshield.core.deps import ContainerDep, SessionDep

router = APIRouter(prefix="/api/v1/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut], summary="List budgets with live spend")
async def list_budgets(_: Viewer, session: SessionDep, container: ContainerDep) -> list[BudgetOut]:
    return await service.list_budgets(session, container.ledger, container.db.sessionmaker)


@router.post("", response_model=BudgetOut, status_code=201, summary="Create a budget")
async def create_budget(
    body: BudgetIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> BudgetOut:
    out = await service.create_budget(session, body, actor)
    await container.config_cache.invalidate()
    return out


@router.patch("/{budget_id}", response_model=BudgetOut, summary="Update a budget")
async def update_budget(
    budget_id: uuid.UUID,
    body: BudgetUpdate,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> BudgetOut:
    out = await service.update_budget(session, budget_id, body, actor)
    await container.config_cache.invalidate()
    return out


@router.delete("/{budget_id}", status_code=204, summary="Delete a budget")
async def delete_budget(
    budget_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Response:
    await service.delete_budget(session, budget_id, actor)
    await container.config_cache.invalidate()
    return Response(status_code=204)
