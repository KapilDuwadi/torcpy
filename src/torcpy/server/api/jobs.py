"""Job API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from torcpy.models.enums import ClaimJobsSortMethod, JobStatus
from torcpy.models.job import Job, JobCreate, JobUpdate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/jobs", tags=["jobs"])


async def _load_job_relations(db: Database, job_id: int) -> dict[str, list[int]]:
    """Load all relationship IDs for a job."""
    deps = await db.fetchall(
        "SELECT depends_on_job_id FROM job_depends_on WHERE job_id = ?", (job_id,)
    )
    input_files = await db.fetchall(
        "SELECT file_id FROM job_input_file WHERE job_id = ?", (job_id,)
    )
    output_files = await db.fetchall(
        "SELECT file_id FROM job_output_file WHERE job_id = ?", (job_id,)
    )
    input_ud = await db.fetchall(
        "SELECT user_data_id FROM job_input_user_data WHERE job_id = ?", (job_id,)
    )
    output_ud = await db.fetchall(
        "SELECT user_data_id FROM job_output_user_data WHERE job_id = ?", (job_id,)
    )
    return {
        "depends_on_job_ids": [r["depends_on_job_id"] for r in deps],
        "input_file_ids": [r["file_id"] for r in input_files],
        "output_file_ids": [r["file_id"] for r in output_files],
        "input_user_data_ids": [r["user_data_id"] for r in input_ud],
        "output_user_data_ids": [r["user_data_id"] for r in output_ud],
    }


async def _row_to_job(db: Database, row: Any) -> Job:
    rels = await _load_job_relations(db, row["id"])
    return Job(
        id=row["id"],
        workflow_id=row["workflow_id"],
        name=row["name"],
        command=row["command"],
        status=JobStatus(row["status"]),
        resource_requirements_id=row["resource_requirements_id"],
        scheduler_id=row["scheduler_id"],
        failure_handler_id=row["failure_handler_id"],
        attempt_id=row["attempt_id"],
        priority=row["priority"],
        unblocking_processed=row["unblocking_processed"],
        cancel_on_blocking_job_failure=bool(row["cancel_on_blocking_job_failure"]),
        supports_termination=bool(row["supports_termination"]),
        **rels,
    )


@router.post("", status_code=201)
async def create_job(workflow_id: int, body: JobCreate, db: Database = Depends(get_db)) -> Job:
    wf = await db.fetchone("SELECT id FROM workflow WHERE id = ?", (workflow_id,))
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    job_id = await db.insert(
        """
        INSERT INTO job (workflow_id, name, command, status, resource_requirements_id,
            scheduler_id, failure_handler_id, priority, cancel_on_blocking_job_failure,
            supports_termination)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            body.name,
            body.command,
            body.status,
            body.resource_requirements_id,
            body.scheduler_id,
            body.failure_handler_id,
            body.priority,
            int(body.cancel_on_blocking_job_failure),
            int(body.supports_termination),
        ),
    )

    # Insert dependency relationships
    if body.depends_on_job_ids:
        await db.executemany(
            "INSERT INTO job_depends_on (job_id, depends_on_job_id, workflow_id) VALUES (?, ?, ?)",
            [(job_id, dep_id, workflow_id) for dep_id in body.depends_on_job_ids],
        )
    if body.input_file_ids:
        await db.executemany(
            "INSERT INTO job_input_file (job_id, file_id, workflow_id) VALUES (?, ?, ?)",
            [(job_id, fid, workflow_id) for fid in body.input_file_ids],
        )
    if body.output_file_ids:
        await db.executemany(
            "INSERT INTO job_output_file (job_id, file_id, workflow_id) VALUES (?, ?, ?)",
            [(job_id, fid, workflow_id) for fid in body.output_file_ids],
        )
    if body.input_user_data_ids:
        await db.executemany(
            "INSERT INTO job_input_user_data (job_id, user_data_id) VALUES (?, ?)",
            [(job_id, uid) for uid in body.input_user_data_ids],
        )
    if body.output_user_data_ids:
        await db.executemany(
            "INSERT INTO job_output_user_data (job_id, user_data_id) VALUES (?, ?)",
            [(job_id, uid) for uid in body.output_user_data_ids],
        )

    await db.conn.commit()
    row = await db.fetchone("SELECT * FROM job WHERE id = ?", (job_id,))
    return await _row_to_job(db, row)


@router.get("")
async def list_jobs(
    workflow_id: int,
    status: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    if status is not None:
        rows = await db.fetchall(
            "SELECT * FROM job WHERE workflow_id = ? AND status = ? ORDER BY id LIMIT ? OFFSET ?",
            (workflow_id, status, lim + 1, off),
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM job WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (workflow_id, lim + 1, off),
        )
    has_more = len(rows) > lim
    items = [await _row_to_job(db, r) for r in rows[:lim]]
    return {"items": items, "offset": off, "limit": lim, "has_more": has_more}


@router.get("/{job_id}")
async def get_job(workflow_id: int, job_id: int, db: Database = Depends(get_db)) -> Job:
    row = await db.fetchone(
        "SELECT * FROM job WHERE id = ? AND workflow_id = ?", (job_id, workflow_id)
    )
    if row is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return await _row_to_job(db, row)


@router.patch("/{job_id}")
async def update_job(
    workflow_id: int,
    job_id: int,
    body: JobUpdate,
    db: Database = Depends(get_db),
) -> Job:
    updates = []
    params: list = []

    for field in (
        "name",
        "command",
        "resource_requirements_id",
        "scheduler_id",
        "failure_handler_id",
        "priority",
    ):
        val = getattr(body, field)
        if val is not None:
            updates.append(f"{field} = ?")
            params.append(val)
    if body.status is not None:
        updates.append("status = ?")
        params.append(int(body.status))
    if body.cancel_on_blocking_job_failure is not None:
        updates.append("cancel_on_blocking_job_failure = ?")
        params.append(int(body.cancel_on_blocking_job_failure))
    if body.supports_termination is not None:
        updates.append("supports_termination = ?")
        params.append(int(body.supports_termination))

    if updates:
        params.append(job_id)
        params.append(workflow_id)
        await db.execute(
            f"UPDATE job SET {', '.join(updates)} WHERE id = ? AND workflow_id = ?",
            tuple(params),
        )
        await db.conn.commit()

    return await get_job(workflow_id, job_id, db)


@router.delete("/{job_id}", status_code=204)
async def delete_job(workflow_id: int, job_id: int, db: Database = Depends(get_db)) -> None:
    result = await db.execute(
        "DELETE FROM job WHERE id = ? AND workflow_id = ?", (job_id, workflow_id)
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"Job {job_id} not found")


@router.post("/claim")
async def claim_next_jobs(
    workflow_id: int,
    request: Request,
    count: int = Query(1, ge=1, le=100),
    compute_node_id: int | None = None,
    sort: ClaimJobsSortMethod = ClaimJobsSortMethod.PRIORITY,
    db: Database = Depends(get_db),
) -> list[Job]:
    """Claim the next available jobs using a write lock to prevent double-allocation."""
    order_clause = "j.priority DESC, j.id ASC"
    if sort == ClaimJobsSortMethod.GPUS_RUNTIME_MEMORY:
        order_clause = """
            COALESCE(rr.num_gpus, 0) DESC,
            COALESCE(rr.runtime_s, 0) DESC,
            COALESCE(rr.memory_bytes, 0) DESC,
            j.id ASC
        """
    elif sort == ClaimJobsSortMethod.CPUS_RUNTIME_MEMORY:
        order_clause = """
            COALESCE(rr.num_cpus, 0) DESC,
            COALESCE(rr.runtime_s, 0) DESC,
            COALESCE(rr.memory_bytes, 0) DESC,
            j.id ASC
        """

    async with db.write_transaction():
        rows = await db.fetchall(
            f"""
            SELECT j.id FROM job j
            LEFT JOIN resource_requirements rr ON rr.id = j.resource_requirements_id
            WHERE j.workflow_id = ? AND j.status = ?
            ORDER BY {order_clause}
            LIMIT ?
            """,
            (workflow_id, JobStatus.READY, count),
        )

        if not rows:
            return []

        job_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(job_ids))
        await db.execute(
            f"UPDATE job SET status = ? WHERE id IN ({placeholders})",
            (JobStatus.PENDING, *job_ids),
        )

        if compute_node_id is not None:
            for jid in job_ids:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO job_internal (job_id, active_compute_node_id)
                    VALUES (?, ?)
                    """,
                    (jid, compute_node_id),
                )

    result = []
    for jid in job_ids:
        row = await db.fetchone("SELECT * FROM job WHERE id = ?", (jid,))
        if row:
            result.append(await _row_to_job(db, row))
    return result


@router.post("/{job_id}/complete")
async def complete_job(
    workflow_id: int,
    job_id: int,
    request: Request,
    status: int = Query(..., ge=5, le=10),
    db: Database = Depends(get_db),
) -> Job:
    """Complete a job and signal the background unblock task."""
    row = await db.fetchone(
        "SELECT * FROM job WHERE id = ? AND workflow_id = ?", (job_id, workflow_id)
    )
    if row is None:
        raise HTTPException(404, f"Job {job_id} not found")

    await db.execute(
        "UPDATE job SET status = ?, unblocking_processed = 0 WHERE id = ?",
        (status, job_id),
    )
    await db.conn.commit()

    # Signal background task
    bg_task = getattr(request.app.state, "bg_unblock", None)
    if bg_task:
        bg_task.signal()

    row = await db.fetchone("SELECT * FROM job WHERE id = ?", (job_id,))
    return await _row_to_job(db, row)


@router.post("/{job_id}/reset")
async def reset_job(
    workflow_id: int,
    job_id: int,
    db: Database = Depends(get_db),
) -> Job:
    """Reset a job back to uninitialized."""
    row = await db.fetchone(
        "SELECT * FROM job WHERE id = ? AND workflow_id = ?", (job_id, workflow_id)
    )
    if row is None:
        raise HTTPException(404, f"Job {job_id} not found")

    await db.execute(
        "UPDATE job SET status = ?, attempt_id = 0, unblocking_processed = 1 WHERE id = ?",
        (JobStatus.UNINITIALIZED, job_id),
    )
    await db.conn.commit()

    row = await db.fetchone("SELECT * FROM job WHERE id = ?", (job_id,))
    return await _row_to_job(db, row)
