"""Resource requirements API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.resource_requirements import (
    ResourceRequirements,
    ResourceRequirementsCreate,
    ResourceRequirementsUpdate,
    parse_memory_to_bytes,
    parse_runtime_to_seconds,
)
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import ResourceRequirementsORM

router = APIRouter(
    prefix="/workflows/{workflow_id}/resource_requirements",
    tags=["resource_requirements"],
)


def _orm_to_rr(obj: ResourceRequirementsORM) -> ResourceRequirements:
    return ResourceRequirements(
        id=obj.id,
        workflow_id=obj.workflow_id,
        num_cpus=obj.num_cpus,
        num_gpus=obj.num_gpus,
        num_nodes=obj.num_nodes,
        memory=obj.memory,
        runtime=obj.runtime,
        memory_bytes=obj.memory_bytes,
        runtime_s=obj.runtime_s,
    )


@router.post("", status_code=201)
async def create_resource_requirements(
    workflow_id: int,
    body: ResourceRequirementsCreate,
    session: AsyncSession = Depends(get_session),
) -> ResourceRequirements:
    memory_bytes = body.memory_bytes or parse_memory_to_bytes(body.memory)
    runtime_s = body.runtime_s or parse_runtime_to_seconds(body.runtime)
    obj = ResourceRequirementsORM(
        workflow_id=workflow_id,
        num_cpus=body.num_cpus,
        num_gpus=body.num_gpus,
        num_nodes=body.num_nodes,
        memory=body.memory,
        runtime=body.runtime,
        memory_bytes=memory_bytes,
        runtime_s=runtime_s,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_rr(obj)


@router.get("")
async def list_resource_requirements(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(ResourceRequirementsORM)
        .where(ResourceRequirementsORM.workflow_id == workflow_id)
        .order_by(ResourceRequirementsORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_rr(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{rr_id}")
async def get_resource_requirements(
    workflow_id: int, rr_id: int, session: AsyncSession = Depends(get_session)
) -> ResourceRequirements:
    stmt = select(ResourceRequirementsORM).where(
        ResourceRequirementsORM.id == rr_id, ResourceRequirementsORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ResourceRequirements {rr_id} not found")
    return _orm_to_rr(obj)


@router.patch("/{rr_id}")
async def update_resource_requirements(
    workflow_id: int,
    rr_id: int,
    body: ResourceRequirementsUpdate,
    session: AsyncSession = Depends(get_session),
) -> ResourceRequirements:
    stmt = select(ResourceRequirementsORM).where(
        ResourceRequirementsORM.id == rr_id, ResourceRequirementsORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ResourceRequirements {rr_id} not found")
    for field in ("num_cpus", "num_gpus", "num_nodes", "memory", "runtime"):
        val = getattr(body, field)
        if val is not None:
            setattr(obj, field, val)
    if body.memory is not None:
        obj.memory_bytes = parse_memory_to_bytes(body.memory)
    if body.runtime is not None:
        obj.runtime_s = parse_runtime_to_seconds(body.runtime)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_rr(obj)


@router.delete("/{rr_id}", status_code=204)
async def delete_resource_requirements(
    workflow_id: int, rr_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(ResourceRequirementsORM).where(
        ResourceRequirementsORM.id == rr_id, ResourceRequirementsORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ResourceRequirements {rr_id} not found")
    await session.delete(obj)
    await session.commit()
