"""Result API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.result import Result, ResultCreate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/results", tags=["results"])


def _row_to_result(row: dict) -> Result:
    return Result(
        id=row["id"],
        workflow_id=row["workflow_id"],
        job_id=row["job_id"],
        run_id=row["run_id"],
        compute_node_id=row["compute_node_id"],
        return_code=row["return_code"],
        exec_time_minutes=row["exec_time_minutes"],
        completion_time=row["completion_time"],
        status=row["status"],
        peak_memory_bytes=row["peak_memory_bytes"],
        avg_memory_bytes=row["avg_memory_bytes"],
        peak_cpu_percent=row["peak_cpu_percent"],
        avg_cpu_percent=row["avg_cpu_percent"],
    )


@router.post("", status_code=201)
async def create_result(
    workflow_id: int, body: ResultCreate, db: Database = Depends(get_db)
) -> Result:
    rid = await db.insert(
        """
        INSERT INTO result (workflow_id, job_id, run_id, compute_node_id, return_code,
            exec_time_minutes, completion_time, status, peak_memory_bytes, avg_memory_bytes,
            peak_cpu_percent, avg_cpu_percent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            body.job_id,
            body.run_id,
            body.compute_node_id,
            body.return_code,
            body.exec_time_minutes,
            body.completion_time,
            body.status,
            body.peak_memory_bytes,
            body.avg_memory_bytes,
            body.peak_cpu_percent,
            body.avg_cpu_percent,
        ),
    )
    row = await db.fetchone("SELECT * FROM result WHERE id = ?", (rid,))
    return _row_to_result(row)  # type: ignore[arg-type]


@router.get("")
async def list_results(
    workflow_id: int,
    job_id: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    if job_id is not None:
        rows = await db.fetchall(
            "SELECT * FROM result WHERE workflow_id = ? AND job_id = ?"
            " ORDER BY id LIMIT ? OFFSET ?",
            (workflow_id, job_id, lim + 1, off),
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM result WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (workflow_id, lim + 1, off),
        )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_result(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{result_id}")
async def get_result(workflow_id: int, result_id: int, db: Database = Depends(get_db)) -> Result:
    row = await db.fetchone(
        "SELECT * FROM result WHERE id = ? AND workflow_id = ?",
        (result_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"Result {result_id} not found")
    return _row_to_result(row)


@router.delete("/{result_id}", status_code=204)
async def delete_result(workflow_id: int, result_id: int, db: Database = Depends(get_db)) -> None:
    result = await db.execute(
        "DELETE FROM result WHERE id = ? AND workflow_id = ?",
        (result_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"Result {result_id} not found")
