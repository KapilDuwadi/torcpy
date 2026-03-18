"""Compute node API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.compute_node import ComputeNode, ComputeNodeCreate, ComputeNodeUpdate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/compute_nodes", tags=["compute_nodes"])


def _row_to_cn(row: dict) -> ComputeNode:
    return ComputeNode(
        id=row["id"],
        workflow_id=row["workflow_id"],
        hostname=row["hostname"],
        pid=row["pid"],
        start_time=row["start_time"],
        is_active=bool(row["is_active"]),
        num_cpus=row["num_cpus"],
        memory_gb=row["memory_gb"],
        num_gpus=row["num_gpus"],
        num_nodes=row["num_nodes"],
        time_limit=row["time_limit"],
        scheduler_config_id=row["scheduler_config_id"],
    )


@router.post("", status_code=201)
async def create_compute_node(
    workflow_id: int, body: ComputeNodeCreate, db: Database = Depends(get_db)
) -> ComputeNode:
    cid = await db.insert(
        """
        INSERT INTO compute_node (workflow_id, hostname, pid, start_time, is_active,
            num_cpus, memory_gb, num_gpus, num_nodes, time_limit, scheduler_config_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            body.hostname,
            body.pid,
            body.start_time,
            int(body.is_active),
            body.num_cpus,
            body.memory_gb,
            body.num_gpus,
            body.num_nodes,
            body.time_limit,
            body.scheduler_config_id,
        ),
    )
    row = await db.fetchone("SELECT * FROM compute_node WHERE id = ?", (cid,))
    return _row_to_cn(row)  # type: ignore[arg-type]


@router.get("")
async def list_compute_nodes(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM compute_node WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_cn(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{node_id}")
async def get_compute_node(
    workflow_id: int, node_id: int, db: Database = Depends(get_db)
) -> ComputeNode:
    row = await db.fetchone(
        "SELECT * FROM compute_node WHERE id = ? AND workflow_id = ?",
        (node_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"ComputeNode {node_id} not found")
    return _row_to_cn(row)


@router.patch("/{node_id}")
async def update_compute_node(
    workflow_id: int,
    node_id: int,
    body: ComputeNodeUpdate,
    db: Database = Depends(get_db),
) -> ComputeNode:
    updates = []
    params: list = []
    if body.hostname is not None:
        updates.append("hostname = ?")
        params.append(body.hostname)
    if body.is_active is not None:
        updates.append("is_active = ?")
        params.append(int(body.is_active))
    if body.num_cpus is not None:
        updates.append("num_cpus = ?")
        params.append(body.num_cpus)
    if body.memory_gb is not None:
        updates.append("memory_gb = ?")
        params.append(body.memory_gb)
    if body.num_gpus is not None:
        updates.append("num_gpus = ?")
        params.append(body.num_gpus)
    if updates:
        params.extend([node_id, workflow_id])
        await db.execute(
            f"UPDATE compute_node SET {', '.join(updates)} WHERE id = ? AND workflow_id = ?",
            tuple(params),
        )
        await db.conn.commit()
    return await get_compute_node(workflow_id, node_id, db)


@router.delete("/{node_id}", status_code=204)
async def delete_compute_node(
    workflow_id: int, node_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM compute_node WHERE id = ? AND workflow_id = ?",
        (node_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"ComputeNode {node_id} not found")
