"""Scheduler API endpoints (local and slurm)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.scheduler import (
    LocalScheduler,
    LocalSchedulerCreate,
    SlurmScheduler,
    SlurmSchedulerCreate,
)
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import LocalSchedulerORM, SlurmSchedulerORM

local_router = APIRouter(prefix="/workflows/{workflow_id}/local_schedulers", tags=["schedulers"])
slurm_router = APIRouter(prefix="/workflows/{workflow_id}/slurm_schedulers", tags=["schedulers"])


# ── Local Scheduler ──


def _orm_to_local(obj: LocalSchedulerORM) -> LocalScheduler:
    return LocalScheduler(
        id=obj.id,
        workflow_id=obj.workflow_id,
        num_cpus=obj.num_cpus,
        memory=obj.memory,
    )


@local_router.post("", status_code=201)
async def create_local_scheduler(
    workflow_id: int, body: LocalSchedulerCreate, session: AsyncSession = Depends(get_session)
) -> LocalScheduler:
    obj = LocalSchedulerORM(workflow_id=workflow_id, num_cpus=body.num_cpus, memory=body.memory)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_local(obj)


@local_router.get("")
async def list_local_schedulers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(LocalSchedulerORM)
        .where(LocalSchedulerORM.workflow_id == workflow_id)
        .order_by(LocalSchedulerORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_local(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@local_router.get("/{scheduler_id}")
async def get_local_scheduler(
    workflow_id: int, scheduler_id: int, session: AsyncSession = Depends(get_session)
) -> LocalScheduler:
    stmt = select(LocalSchedulerORM).where(
        LocalSchedulerORM.id == scheduler_id, LocalSchedulerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"LocalScheduler {scheduler_id} not found")
    return _orm_to_local(obj)


@local_router.delete("/{scheduler_id}", status_code=204)
async def delete_local_scheduler(
    workflow_id: int, scheduler_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(LocalSchedulerORM).where(
        LocalSchedulerORM.id == scheduler_id, LocalSchedulerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"LocalScheduler {scheduler_id} not found")
    await session.delete(obj)
    await session.commit()


# ── Slurm Scheduler ──


def _orm_to_slurm(obj: SlurmSchedulerORM) -> SlurmScheduler:
    sc = obj.slurm_config
    if isinstance(sc, str):
        try:
            sc = json.loads(sc)
        except (json.JSONDecodeError, TypeError):
            sc = None
    return SlurmScheduler(
        id=obj.id,
        workflow_id=obj.workflow_id,
        account=obj.account,
        partition=obj.partition,
        slurm_config=sc,
    )


@slurm_router.post("", status_code=201)
async def create_slurm_scheduler(
    workflow_id: int, body: SlurmSchedulerCreate, session: AsyncSession = Depends(get_session)
) -> SlurmScheduler:
    obj = SlurmSchedulerORM(
        workflow_id=workflow_id,
        account=body.account,
        partition=body.partition,
        slurm_config=json.dumps(body.slurm_config) if body.slurm_config else None,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_slurm(obj)


@slurm_router.get("")
async def list_slurm_schedulers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(SlurmSchedulerORM)
        .where(SlurmSchedulerORM.workflow_id == workflow_id)
        .order_by(SlurmSchedulerORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_slurm(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@slurm_router.get("/{scheduler_id}")
async def get_slurm_scheduler(
    workflow_id: int, scheduler_id: int, session: AsyncSession = Depends(get_session)
) -> SlurmScheduler:
    stmt = select(SlurmSchedulerORM).where(
        SlurmSchedulerORM.id == scheduler_id, SlurmSchedulerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"SlurmScheduler {scheduler_id} not found")
    return _orm_to_slurm(obj)


@slurm_router.delete("/{scheduler_id}", status_code=204)
async def delete_slurm_scheduler(
    workflow_id: int, scheduler_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(SlurmSchedulerORM).where(
        SlurmSchedulerORM.id == scheduler_id, SlurmSchedulerORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"SlurmScheduler {scheduler_id} not found")
    await session.delete(obj)
    await session.commit()
