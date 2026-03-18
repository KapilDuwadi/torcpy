"""Workflow API endpoints."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.enums import JobStatus
from torcpy.models.workflow import Workflow, WorkflowCreate, WorkflowStatus, WorkflowUpdate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _row_to_workflow(row: dict) -> Workflow:
    return Workflow(
        id=row["id"],
        name=row["name"],
        user=row["user"],
        timestamp=row["timestamp"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
        slurm_defaults=json.loads(row["slurm_defaults"]) if row["slurm_defaults"] else None,
        resource_monitor_config=(
            json.loads(row["resource_monitor_config"]) if row["resource_monitor_config"] else None
        ),
        execution_config=(json.loads(row["execution_config"]) if row["execution_config"] else None),
        use_pending_failed=bool(row["use_pending_failed"]),
        project=row["project"],
        status=WorkflowStatus(
            workflow_id=row["id"],
            run_id=row["run_id"] if "run_id" in row.keys() else 0,
            is_archived=bool(row["is_archived"]) if "is_archived" in row.keys() else False,
            is_canceled=bool(row["is_canceled"]) if "is_canceled" in row.keys() else False,
        ),
    )


@router.post("", status_code=201)
async def create_workflow(body: WorkflowCreate, db: Database = Depends(get_db)) -> Workflow:
    now = time.time()
    user = body.user or "anonymous"
    wf_id = await db.insert(
        """
        INSERT INTO workflow (name, user, timestamp, metadata, slurm_defaults,
            resource_monitor_config, execution_config, use_pending_failed, project)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body.name,
            user,
            now,
            json.dumps(body.metadata) if body.metadata else None,
            json.dumps(body.slurm_defaults) if body.slurm_defaults else None,
            json.dumps(body.resource_monitor_config) if body.resource_monitor_config else None,
            json.dumps(body.execution_config) if body.execution_config else None,
            int(body.use_pending_failed),
            body.project,
        ),
    )
    await db.execute(
        "INSERT INTO workflow_status"
        " (workflow_id, run_id, is_archived, is_canceled) VALUES (?,0,0,0)",
        (wf_id,),
    )
    await db.conn.commit()
    row = await db.fetchone(
        """
        SELECT w.*, ws.run_id, ws.is_archived, ws.is_canceled
        FROM workflow w
        JOIN workflow_status ws ON ws.workflow_id = w.id
        WHERE w.id = ?
        """,
        (wf_id,),
    )
    return _row_to_workflow(row)  # type: ignore[arg-type]


@router.get("")
async def list_workflows(
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        """
        SELECT w.*, ws.run_id, ws.is_archived, ws.is_canceled
        FROM workflow w
        JOIN workflow_status ws ON ws.workflow_id = w.id
        ORDER BY w.id DESC
        LIMIT ? OFFSET ?
        """,
        (lim + 1, off),
    )
    has_more = len(rows) > lim
    items = [_row_to_workflow(r) for r in rows[:lim]]
    return {"items": items, "offset": off, "limit": lim, "has_more": has_more}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: int, db: Database = Depends(get_db)) -> Workflow:
    row = await db.fetchone(
        """
        SELECT w.*, ws.run_id, ws.is_archived, ws.is_canceled
        FROM workflow w
        JOIN workflow_status ws ON ws.workflow_id = w.id
        WHERE w.id = ?
        """,
        (workflow_id,),
    )
    if row is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    return _row_to_workflow(row)


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: int, body: WorkflowUpdate, db: Database = Depends(get_db)
) -> Workflow:
    updates = []
    params: list = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.metadata is not None:
        updates.append("metadata = ?")
        params.append(json.dumps(body.metadata))
    if body.slurm_defaults is not None:
        updates.append("slurm_defaults = ?")
        params.append(json.dumps(body.slurm_defaults))
    if body.resource_monitor_config is not None:
        updates.append("resource_monitor_config = ?")
        params.append(json.dumps(body.resource_monitor_config))
    if body.execution_config is not None:
        updates.append("execution_config = ?")
        params.append(json.dumps(body.execution_config))
    if body.use_pending_failed is not None:
        updates.append("use_pending_failed = ?")
        params.append(int(body.use_pending_failed))
    if body.project is not None:
        updates.append("project = ?")
        params.append(body.project)

    if updates:
        params.append(workflow_id)
        await db.execute(
            f"UPDATE workflow SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        await db.conn.commit()

    return await get_workflow(workflow_id, db)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: int, db: Database = Depends(get_db)) -> None:
    result = await db.execute("DELETE FROM workflow WHERE id = ?", (workflow_id,))
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"Workflow {workflow_id} not found")


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: int, db: Database = Depends(get_db)) -> dict:
    row = await db.fetchone("SELECT id FROM workflow WHERE id = ?", (workflow_id,))
    if row is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    await db.execute(
        "UPDATE workflow_status SET is_canceled = 1 WHERE workflow_id = ?",
        (workflow_id,),
    )
    # Cancel all non-terminal jobs
    await db.execute(
        """
        UPDATE job SET status = ?
        WHERE workflow_id = ? AND status IN (?, ?, ?, ?)
        """,
        (
            JobStatus.CANCELED,
            workflow_id,
            JobStatus.UNINITIALIZED,
            JobStatus.BLOCKED,
            JobStatus.READY,
            JobStatus.PENDING,
        ),
    )
    await db.conn.commit()
    return {"status": "canceled", "workflow_id": workflow_id}


@router.post("/{workflow_id}/initialize")
async def initialize_workflow(workflow_id: int, db: Database = Depends(get_db)) -> dict:
    """Initialize jobs: build dependency graph and set initial statuses."""
    row = await db.fetchone("SELECT id FROM workflow WHERE id = ?", (workflow_id,))
    if row is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    # Build implicit dependencies from file relationships
    # If job A outputs file F and job B inputs file F, then B depends on A
    await db.execute(
        """
        INSERT OR IGNORE INTO job_depends_on (job_id, depends_on_job_id, workflow_id)
        SELECT jif.job_id, jof.job_id, jif.workflow_id
        FROM job_input_file jif
        JOIN job_output_file jof ON jof.file_id = jif.file_id
        WHERE jif.workflow_id = ? AND jif.job_id != jof.job_id
        """,
        (workflow_id,),
    )

    # Same for user_data
    await db.execute(
        """
        INSERT OR IGNORE INTO job_depends_on (job_id, depends_on_job_id, workflow_id)
        SELECT jiud.job_id, joud.job_id, ?
        FROM job_input_user_data jiud
        JOIN job_output_user_data joud ON joud.user_data_id = jiud.user_data_id
        JOIN job j1 ON j1.id = jiud.job_id
        JOIN job j2 ON j2.id = joud.job_id
        WHERE j1.workflow_id = ? AND j2.workflow_id = ? AND jiud.job_id != joud.job_id
        """,
        (workflow_id, workflow_id, workflow_id),
    )

    # Jobs with no dependencies -> READY, others -> BLOCKED
    # First set all uninitialized to BLOCKED
    await db.execute(
        "UPDATE job SET status = ? WHERE workflow_id = ? AND status = ?",
        (JobStatus.BLOCKED, workflow_id, JobStatus.UNINITIALIZED),
    )

    # Then set jobs with no unmet dependencies to READY
    await db.execute(
        """
        UPDATE job SET status = ?
        WHERE workflow_id = ? AND status = ?
          AND id NOT IN (
            SELECT DISTINCT jdo.job_id FROM job_depends_on jdo
            WHERE jdo.workflow_id = ?
          )
        """,
        (JobStatus.READY, workflow_id, JobStatus.BLOCKED, workflow_id),
    )

    await db.conn.commit()

    ready = await db.fetchone(
        "SELECT COUNT(*) as cnt FROM job WHERE workflow_id = ? AND status = ?",
        (workflow_id, JobStatus.READY),
    )
    blocked = await db.fetchone(
        "SELECT COUNT(*) as cnt FROM job WHERE workflow_id = ? AND status = ?",
        (workflow_id, JobStatus.BLOCKED),
    )

    return {
        "status": "initialized",
        "workflow_id": workflow_id,
        "ready_jobs": ready["cnt"] if ready else 0,
        "blocked_jobs": blocked["cnt"] if blocked else 0,
    }


@router.post("/{workflow_id}/reset")
async def reset_workflow(workflow_id: int, db: Database = Depends(get_db)) -> dict:
    """Reset all jobs back to uninitialized and increment run_id."""
    row = await db.fetchone("SELECT id FROM workflow WHERE id = ?", (workflow_id,))
    if row is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    await db.execute(
        "UPDATE job SET status = ?, attempt_id = 0, unblocking_processed = 1 WHERE workflow_id = ?",
        (JobStatus.UNINITIALIZED, workflow_id),
    )
    await db.execute(
        "UPDATE workflow_status SET run_id = run_id + 1, is_canceled = 0 WHERE workflow_id = ?",
        (workflow_id,),
    )
    await db.conn.commit()
    return {"status": "reset", "workflow_id": workflow_id}


@router.get("/{workflow_id}/status")
async def workflow_status(workflow_id: int, db: Database = Depends(get_db)) -> dict:
    """Get workflow status summary with job counts by status."""
    row = await db.fetchone("SELECT id FROM workflow WHERE id = ?", (workflow_id,))
    if row is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    counts = await db.fetchall(
        "SELECT status, COUNT(*) as cnt FROM job WHERE workflow_id = ? GROUP BY status",
        (workflow_id,),
    )

    status_counts = {JobStatus(r["status"]).name.lower(): r["cnt"] for r in counts}
    total = sum(r["cnt"] for r in counts)

    ws_row = await db.fetchone(
        "SELECT * FROM workflow_status WHERE workflow_id = ?", (workflow_id,)
    )

    return {
        "workflow_id": workflow_id,
        "run_id": ws_row["run_id"] if ws_row else 0,
        "is_canceled": bool(ws_row["is_canceled"]) if ws_row else False,
        "total_jobs": total,
        "job_status_counts": status_counts,
    }
