"""Compute node API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.compute_node import ComputeNode, ComputeNodeCreate, ComputeNodeUpdate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import ComputeNodeORM

router = APIRouter(prefix="/workflows/{workflow_id}/compute_nodes", tags=["compute_nodes"])


def _orm_to_cn(obj: ComputeNodeORM) -> ComputeNode:
    return ComputeNode(
        id=obj.id,
        workflow_id=obj.workflow_id,
        hostname=obj.hostname,
        pid=obj.pid,
        start_time=obj.start_time,
        is_active=bool(obj.is_active),
        num_cpus=obj.num_cpus,
        memory_gb=obj.memory_gb,
        num_gpus=obj.num_gpus,
        num_nodes=obj.num_nodes,
        time_limit=obj.time_limit,
        scheduler_config_id=obj.scheduler_config_id,
    )


@router.post("", status_code=201)
async def create_compute_node(
    workflow_id: int, body: ComputeNodeCreate, session: AsyncSession = Depends(get_session)
) -> ComputeNode:
    obj = ComputeNodeORM(
        workflow_id=workflow_id,
        hostname=body.hostname,
        pid=body.pid,
        start_time=body.start_time,
        is_active=int(body.is_active),
        num_cpus=body.num_cpus,
        memory_gb=body.memory_gb,
        num_gpus=body.num_gpus,
        num_nodes=body.num_nodes,
        time_limit=body.time_limit,
        scheduler_config_id=body.scheduler_config_id,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_cn(obj)


@router.get("")
async def list_compute_nodes(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(ComputeNodeORM)
        .where(ComputeNodeORM.workflow_id == workflow_id)
        .order_by(ComputeNodeORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_cn(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{node_id}")
async def get_compute_node(
    workflow_id: int, node_id: int, session: AsyncSession = Depends(get_session)
) -> ComputeNode:
    stmt = select(ComputeNodeORM).where(
        ComputeNodeORM.id == node_id, ComputeNodeORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ComputeNode {node_id} not found")
    return _orm_to_cn(obj)


@router.patch("/{node_id}")
async def update_compute_node(
    workflow_id: int,
    node_id: int,
    body: ComputeNodeUpdate,
    session: AsyncSession = Depends(get_session),
) -> ComputeNode:
    stmt = select(ComputeNodeORM).where(
        ComputeNodeORM.id == node_id, ComputeNodeORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ComputeNode {node_id} not found")
    if body.hostname is not None:
        obj.hostname = body.hostname
    if body.is_active is not None:
        obj.is_active = int(body.is_active)
    if body.num_cpus is not None:
        obj.num_cpus = body.num_cpus
    if body.memory_gb is not None:
        obj.memory_gb = body.memory_gb
    if body.num_gpus is not None:
        obj.num_gpus = body.num_gpus
    await session.commit()
    await session.refresh(obj)
    return _orm_to_cn(obj)


@router.delete("/{node_id}", status_code=204)
async def delete_compute_node(
    workflow_id: int, node_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(ComputeNodeORM).where(
        ComputeNodeORM.id == node_id, ComputeNodeORM.workflow_id == workflow_id
    )
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"ComputeNode {node_id} not found")
    await session.delete(obj)
    await session.commit()
