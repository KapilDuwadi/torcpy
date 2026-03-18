"""Event API endpoints."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.event import Event, EventCreate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import EventORM

router = APIRouter(prefix="/workflows/{workflow_id}/events", tags=["events"])


def _orm_to_event(obj: EventORM) -> Event:
    data = obj.data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return Event(
        id=obj.id,
        workflow_id=obj.workflow_id,
        timestamp=obj.timestamp,
        data=data,
    )


@router.post("", status_code=201)
async def create_event(
    workflow_id: int, body: EventCreate, session: AsyncSession = Depends(get_session)
) -> Event:
    ts = body.timestamp or int(time.time())
    obj = EventORM(
        workflow_id=workflow_id,
        timestamp=ts,
        data=json.dumps(body.data) if body.data else None,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_event(obj)


@router.get("")
async def list_events(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(EventORM)
        .where(EventORM.workflow_id == workflow_id)
        .order_by(EventORM.id.desc())
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_event(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{event_id}")
async def get_event(
    workflow_id: int, event_id: int, session: AsyncSession = Depends(get_session)
) -> Event:
    stmt = select(EventORM).where(EventORM.id == event_id, EventORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Event {event_id} not found")
    return _orm_to_event(obj)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    workflow_id: int, event_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(EventORM).where(EventORM.id == event_id, EventORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Event {event_id} not found")
    await session.delete(obj)
    await session.commit()
