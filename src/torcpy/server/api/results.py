"""Result API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.result import Result, ResultCreate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import ResultORM

router = APIRouter(prefix="/workflows/{workflow_id}/results", tags=["results"])


def _orm_to_result(obj: ResultORM) -> Result:
    return Result(
        id=obj.id,
        workflow_id=obj.workflow_id,
        job_id=obj.job_id,
        run_id=obj.run_id,
        compute_node_id=obj.compute_node_id,
        return_code=obj.return_code,
        exec_time_minutes=obj.exec_time_minutes,
        completion_time=obj.completion_time,
        status=obj.status,
        peak_memory_bytes=obj.peak_memory_bytes,
        avg_memory_bytes=obj.avg_memory_bytes,
        peak_cpu_percent=obj.peak_cpu_percent,
        avg_cpu_percent=obj.avg_cpu_percent,
    )


@router.post("", status_code=201)
async def create_result(
    workflow_id: int, body: ResultCreate, session: AsyncSession = Depends(get_session)
) -> Result:
    obj = ResultORM(
        workflow_id=workflow_id,
        job_id=body.job_id,
        run_id=body.run_id,
        compute_node_id=body.compute_node_id,
        return_code=body.return_code,
        exec_time_minutes=body.exec_time_minutes,
        completion_time=body.completion_time,
        status=body.status,
        peak_memory_bytes=body.peak_memory_bytes,
        avg_memory_bytes=body.avg_memory_bytes,
        peak_cpu_percent=body.peak_cpu_percent,
        avg_cpu_percent=body.avg_cpu_percent,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_result(obj)


@router.get("")
async def list_results(
    workflow_id: int,
    job_id: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = select(ResultORM).where(ResultORM.workflow_id == workflow_id)
    if job_id is not None:
        stmt = stmt.where(ResultORM.job_id == job_id)
    stmt = stmt.order_by(ResultORM.id).offset(off).limit(lim + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_result(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{result_id}")
async def get_result(
    workflow_id: int, result_id: int, session: AsyncSession = Depends(get_session)
) -> Result:
    stmt = select(ResultORM).where(ResultORM.id == result_id, ResultORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Result {result_id} not found")
    return _orm_to_result(obj)


@router.delete("/{result_id}", status_code=204)
async def delete_result(
    workflow_id: int, result_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(ResultORM).where(ResultORM.id == result_id, ResultORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Result {result_id} not found")
    await session.delete(obj)
    await session.commit()
