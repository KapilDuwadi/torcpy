"""Failure handler API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.failure_handler import FailureHandler, FailureHandlerCreate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import FailureHandlerORM

router = APIRouter(prefix="/workflows/{workflow_id}/failure_handlers", tags=["failure_handlers"])


def _orm_to_fh(obj: FailureHandlerORM) -> FailureHandler:
    rules = obj.rules
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            rules = []
    return FailureHandler(
        id=obj.id,
        workflow_id=obj.workflow_id,
        name=obj.name,
        rules=rules or [],
        default_max_retries=obj.default_max_retries,
        default_recovery_command=obj.default_recovery_command,
    )


@router.post("", status_code=201)
async def create_failure_handler(
    workflow_id: int,
    body: FailureHandlerCreate,
    session: AsyncSession = Depends(get_session),
) -> FailureHandler:
    obj = FailureHandlerORM(
        workflow_id=workflow_id,
        name=body.name,
        rules=json.dumps([r.model_dump() for r in body.rules]),
        default_max_retries=body.default_max_retries,
        default_recovery_command=body.default_recovery_command,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_fh(obj)


@router.get("")
async def list_failure_handlers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(FailureHandlerORM)
        .where(FailureHandlerORM.workflow_id == workflow_id)
        .order_by(FailureHandlerORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_fh(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{fh_id}")
async def get_failure_handler(
    workflow_id: int, fh_id: int, session: AsyncSession = Depends(get_session)
) -> FailureHandler:
    stmt = select(FailureHandlerORM).where(
        FailureHandlerORM.id == fh_id, FailureHandlerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"FailureHandler {fh_id} not found")
    return _orm_to_fh(obj)


@router.delete("/{fh_id}", status_code=204)
async def delete_failure_handler(
    workflow_id: int, fh_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(FailureHandlerORM).where(
        FailureHandlerORM.id == fh_id, FailureHandlerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"FailureHandler {fh_id} not found")
    await session.delete(obj)
    await session.commit()
