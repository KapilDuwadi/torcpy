"""User data API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.user_data import UserData, UserDataCreate, UserDataUpdate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import UserDataORM

router = APIRouter(prefix="/workflows/{workflow_id}/user_data", tags=["user_data"])


def _orm_to_user_data(obj: UserDataORM) -> UserData:
    data = obj.data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return UserData(
        id=obj.id,
        workflow_id=obj.workflow_id,
        name=obj.name,
        data=data,
        is_ephemeral=bool(obj.is_ephemeral),
    )


@router.post("", status_code=201)
async def create_user_data(
    workflow_id: int, body: UserDataCreate, session: AsyncSession = Depends(get_session)
) -> UserData:
    obj = UserDataORM(
        workflow_id=workflow_id,
        name=body.name,
        data=json.dumps(body.data) if body.data is not None else None,
        is_ephemeral=int(body.is_ephemeral),
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_user_data(obj)


@router.get("")
async def list_user_data(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(UserDataORM)
        .where(UserDataORM.workflow_id == workflow_id)
        .order_by(UserDataORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_user_data(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{user_data_id}")
async def get_user_data(
    workflow_id: int, user_data_id: int, session: AsyncSession = Depends(get_session)
) -> UserData:
    stmt = select(UserDataORM).where(
        UserDataORM.id == user_data_id, UserDataORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"UserData {user_data_id} not found")
    return _orm_to_user_data(obj)


@router.patch("/{user_data_id}")
async def update_user_data(
    workflow_id: int,
    user_data_id: int,
    body: UserDataUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserData:
    stmt = select(UserDataORM).where(
        UserDataORM.id == user_data_id, UserDataORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"UserData {user_data_id} not found")
    if body.name is not None:
        obj.name = body.name
    if body.data is not None:
        obj.data = json.dumps(body.data)
    if body.is_ephemeral is not None:
        obj.is_ephemeral = int(body.is_ephemeral)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_user_data(obj)


@router.delete("/{user_data_id}", status_code=204)
async def delete_user_data(
    workflow_id: int, user_data_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(UserDataORM).where(
        UserDataORM.id == user_data_id, UserDataORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"UserData {user_data_id} not found")
    await session.delete(obj)
    await session.commit()
