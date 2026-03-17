"""Resource requirements API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.resource_requirements import (
    ResourceRequirements,
    ResourceRequirementsCreate,
    ResourceRequirementsUpdate,
    parse_memory_to_bytes,
    parse_runtime_to_seconds,
)
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(
    prefix="/workflows/{workflow_id}/resource_requirements",
    tags=["resource_requirements"],
)


def _row_to_rr(row: dict) -> ResourceRequirements:
    return ResourceRequirements(
        id=row["id"],
        workflow_id=row["workflow_id"],
        num_cpus=row["num_cpus"],
        num_gpus=row["num_gpus"],
        num_nodes=row["num_nodes"],
        memory=row["memory"],
        runtime=row["runtime"],
        memory_bytes=row["memory_bytes"],
        runtime_s=row["runtime_s"],
    )


@router.post("", status_code=201)
async def create_resource_requirements(
    workflow_id: int,
    body: ResourceRequirementsCreate,
    db: Database = Depends(get_db),
) -> ResourceRequirements:
    memory_bytes = body.memory_bytes or parse_memory_to_bytes(body.memory)
    runtime_s = body.runtime_s or parse_runtime_to_seconds(body.runtime)

    rid = await db.insert(
        """
        INSERT INTO resource_requirements
            (workflow_id, num_cpus, num_gpus, num_nodes, memory, runtime, memory_bytes, runtime_s)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            body.num_cpus,
            body.num_gpus,
            body.num_nodes,
            body.memory,
            body.runtime,
            memory_bytes,
            runtime_s,
        ),
    )
    row = await db.fetchone("SELECT * FROM resource_requirements WHERE id = ?", (rid,))
    return _row_to_rr(row)  # type: ignore[arg-type]


@router.get("")
async def list_resource_requirements(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM resource_requirements WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_rr(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{rr_id}")
async def get_resource_requirements(
    workflow_id: int, rr_id: int, db: Database = Depends(get_db)
) -> ResourceRequirements:
    row = await db.fetchone(
        "SELECT * FROM resource_requirements WHERE id = ? AND workflow_id = ?",
        (rr_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"ResourceRequirements {rr_id} not found")
    return _row_to_rr(row)


@router.patch("/{rr_id}")
async def update_resource_requirements(
    workflow_id: int,
    rr_id: int,
    body: ResourceRequirementsUpdate,
    db: Database = Depends(get_db),
) -> ResourceRequirements:
    updates = []
    params: list = []
    for field in ("num_cpus", "num_gpus", "num_nodes", "memory", "runtime"):
        val = getattr(body, field)
        if val is not None:
            updates.append(f"{field} = ?")
            params.append(val)
    if body.memory is not None:
        updates.append("memory_bytes = ?")
        params.append(parse_memory_to_bytes(body.memory))
    if body.runtime is not None:
        updates.append("runtime_s = ?")
        params.append(parse_runtime_to_seconds(body.runtime))
    if updates:
        params.extend([rr_id, workflow_id])
        await db.execute(
            f"UPDATE resource_requirements SET {', '.join(updates)} WHERE id = ? AND workflow_id = ?",
            tuple(params),
        )
        await db.conn.commit()
    return await get_resource_requirements(workflow_id, rr_id, db)


@router.delete("/{rr_id}", status_code=204)
async def delete_resource_requirements(
    workflow_id: int, rr_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM resource_requirements WHERE id = ? AND workflow_id = ?",
        (rr_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"ResourceRequirements {rr_id} not found")
