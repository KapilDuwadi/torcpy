"""Scheduler API endpoints (local and slurm)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.scheduler import (
    LocalScheduler,
    LocalSchedulerCreate,
    SlurmScheduler,
    SlurmSchedulerCreate,
)
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

local_router = APIRouter(prefix="/workflows/{workflow_id}/local_schedulers", tags=["schedulers"])
slurm_router = APIRouter(prefix="/workflows/{workflow_id}/slurm_schedulers", tags=["schedulers"])


# ── Local Scheduler ──


def _row_to_local(row: dict) -> LocalScheduler:
    return LocalScheduler(
        id=row["id"],
        workflow_id=row["workflow_id"],
        num_cpus=row["num_cpus"],
        memory=row["memory"],
    )


@local_router.post("", status_code=201)
async def create_local_scheduler(
    workflow_id: int, body: LocalSchedulerCreate, db: Database = Depends(get_db)
) -> LocalScheduler:
    sid = await db.insert(
        "INSERT INTO local_scheduler (workflow_id, num_cpus, memory) VALUES (?, ?, ?)",
        (workflow_id, body.num_cpus, body.memory),
    )
    row = await db.fetchone("SELECT * FROM local_scheduler WHERE id = ?", (sid,))
    return _row_to_local(row)  # type: ignore[arg-type]


@local_router.get("")
async def list_local_schedulers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM local_scheduler WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_local(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@local_router.get("/{scheduler_id}")
async def get_local_scheduler(
    workflow_id: int, scheduler_id: int, db: Database = Depends(get_db)
) -> LocalScheduler:
    row = await db.fetchone(
        "SELECT * FROM local_scheduler WHERE id = ? AND workflow_id = ?",
        (scheduler_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"LocalScheduler {scheduler_id} not found")
    return _row_to_local(row)


@local_router.delete("/{scheduler_id}", status_code=204)
async def delete_local_scheduler(
    workflow_id: int, scheduler_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM local_scheduler WHERE id = ? AND workflow_id = ?",
        (scheduler_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"LocalScheduler {scheduler_id} not found")


# ── Slurm Scheduler ──


def _row_to_slurm(row: dict) -> SlurmScheduler:
    sc = row["slurm_config"]
    if isinstance(sc, str):
        try:
            sc = json.loads(sc)
        except (json.JSONDecodeError, TypeError):
            sc = None
    return SlurmScheduler(
        id=row["id"],
        workflow_id=row["workflow_id"],
        account=row["account"],
        partition=row["partition"],
        slurm_config=sc,
    )


@slurm_router.post("", status_code=201)
async def create_slurm_scheduler(
    workflow_id: int, body: SlurmSchedulerCreate, db: Database = Depends(get_db)
) -> SlurmScheduler:
    sid = await db.insert(
        "INSERT INTO slurm_scheduler"
        " (workflow_id, account, partition, slurm_config) VALUES (?,?,?,?)",
        (
            workflow_id,
            body.account,
            body.partition,
            json.dumps(body.slurm_config) if body.slurm_config else None,
        ),
    )
    row = await db.fetchone("SELECT * FROM slurm_scheduler WHERE id = ?", (sid,))
    return _row_to_slurm(row)  # type: ignore[arg-type]


@slurm_router.get("")
async def list_slurm_schedulers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM slurm_scheduler WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_slurm(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@slurm_router.get("/{scheduler_id}")
async def get_slurm_scheduler(
    workflow_id: int, scheduler_id: int, db: Database = Depends(get_db)
) -> SlurmScheduler:
    row = await db.fetchone(
        "SELECT * FROM slurm_scheduler WHERE id = ? AND workflow_id = ?",
        (scheduler_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"SlurmScheduler {scheduler_id} not found")
    return _row_to_slurm(row)


@slurm_router.delete("/{scheduler_id}", status_code=204)
async def delete_slurm_scheduler(
    workflow_id: int, scheduler_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM slurm_scheduler WHERE id = ? AND workflow_id = ?",
        (scheduler_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"SlurmScheduler {scheduler_id} not found")
