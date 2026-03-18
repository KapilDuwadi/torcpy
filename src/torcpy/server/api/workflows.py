"""Workflow API endpoints."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.enums import JobStatus
from torcpy.models.workflow import Workflow, WorkflowCreate, WorkflowStatus, WorkflowUpdate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import JobORM, WorkflowORM, WorkflowStatusORM

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _orm_to_workflow(wf: WorkflowORM) -> Workflow:
    ws = wf.status
    return Workflow(
        id=wf.id,
        name=wf.name,
        user=wf.user,
        timestamp=wf.timestamp,
        metadata=json.loads(wf.metadata_) if wf.metadata_ else None,
        slurm_defaults=json.loads(wf.slurm_defaults) if wf.slurm_defaults else None,
        resource_monitor_config=(
            json.loads(wf.resource_monitor_config) if wf.resource_monitor_config else None
        ),
        execution_config=json.loads(wf.execution_config) if wf.execution_config else None,
        use_pending_failed=bool(wf.use_pending_failed),
        project=wf.project,
        status=WorkflowStatus(
            workflow_id=wf.id,
            run_id=ws.run_id if ws else 0,
            is_archived=bool(ws.is_archived) if ws else False,
            is_canceled=bool(ws.is_canceled) if ws else False,
        ),
    )


@router.post("", status_code=201)
async def create_workflow(
    body: WorkflowCreate, session: AsyncSession = Depends(get_session)
) -> Workflow:
    now = time.time()
    user = body.user or "anonymous"
    wf = WorkflowORM(
        name=body.name,
        user=user,
        timestamp=now,
        metadata_=json.dumps(body.metadata) if body.metadata else None,
        slurm_defaults=json.dumps(body.slurm_defaults) if body.slurm_defaults else None,
        resource_monitor_config=(
            json.dumps(body.resource_monitor_config) if body.resource_monitor_config else None
        ),
        execution_config=json.dumps(body.execution_config) if body.execution_config else None,
        use_pending_failed=int(body.use_pending_failed),
        project=body.project,
    )
    session.add(wf)
    await session.flush()

    ws = WorkflowStatusORM(workflow_id=wf.id, run_id=0, is_archived=0, is_canceled=0)
    session.add(ws)
    await session.commit()

    # Re-fetch with joined status
    result = await session.execute(select(WorkflowORM).where(WorkflowORM.id == wf.id))
    wf_obj = result.scalar_one()
    return _orm_to_workflow(wf_obj)


@router.get("")
async def list_workflows(
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = select(WorkflowORM).order_by(WorkflowORM.id.desc()).offset(off).limit(lim + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().unique().all())
    has_more = len(rows) > lim
    items = [_orm_to_workflow(r) for r in rows[:lim]]
    return {"items": items, "offset": off, "limit": lim, "has_more": has_more}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: int, session: AsyncSession = Depends(get_session)) -> Workflow:
    stmt = select(WorkflowORM).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    return _orm_to_workflow(wf)


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: int,
    body: WorkflowUpdate,
    session: AsyncSession = Depends(get_session),
) -> Workflow:
    stmt = select(WorkflowORM).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    if body.name is not None:
        wf.name = body.name
    if body.metadata is not None:
        wf.metadata_ = json.dumps(body.metadata)
    if body.slurm_defaults is not None:
        wf.slurm_defaults = json.dumps(body.slurm_defaults)
    if body.resource_monitor_config is not None:
        wf.resource_monitor_config = json.dumps(body.resource_monitor_config)
    if body.execution_config is not None:
        wf.execution_config = json.dumps(body.execution_config)
    if body.use_pending_failed is not None:
        wf.use_pending_failed = int(body.use_pending_failed)
    if body.project is not None:
        wf.project = body.project

    await session.commit()
    await session.refresh(wf)
    return _orm_to_workflow(wf)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: int, session: AsyncSession = Depends(get_session)) -> None:
    stmt = select(WorkflowORM).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")
    await session.delete(wf)
    await session.commit()


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    stmt = select(WorkflowORM.id).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    await session.execute(
        update(WorkflowStatusORM)
        .where(WorkflowStatusORM.workflow_id == workflow_id)
        .values(is_canceled=1)
    )
    await session.execute(
        update(JobORM)
        .where(
            JobORM.workflow_id == workflow_id,
            JobORM.status.in_(
                [
                    int(JobStatus.UNINITIALIZED),
                    int(JobStatus.BLOCKED),
                    int(JobStatus.READY),
                    int(JobStatus.PENDING),
                ]
            ),
        )
        .values(status=int(JobStatus.CANCELED))
    )
    await session.commit()
    return {"status": "canceled", "workflow_id": workflow_id}


@router.post("/{workflow_id}/initialize")
async def initialize_workflow(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Initialize jobs: build dependency graph and set initial statuses."""
    stmt = select(WorkflowORM.id).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    # Build implicit dependencies from file relationships (kept as text — too complex for ORM)
    await session.execute(
        text(
            """
            INSERT OR IGNORE INTO job_depends_on (job_id, depends_on_job_id, workflow_id)
            SELECT jif.job_id, jof.job_id, jif.workflow_id
            FROM job_input_file jif
            JOIN job_output_file jof ON jof.file_id = jif.file_id
            WHERE jif.workflow_id = :wf_id AND jif.job_id != jof.job_id
            """
        ),
        {"wf_id": workflow_id},
    )

    # Same for user_data
    await session.execute(
        text(
            """
            INSERT OR IGNORE INTO job_depends_on (job_id, depends_on_job_id, workflow_id)
            SELECT jiud.job_id, joud.job_id, :wf_id
            FROM job_input_user_data jiud
            JOIN job_output_user_data joud ON joud.user_data_id = jiud.user_data_id
            JOIN job j1 ON j1.id = jiud.job_id
            JOIN job j2 ON j2.id = joud.job_id
            WHERE j1.workflow_id = :wf_id AND j2.workflow_id = :wf_id
              AND jiud.job_id != joud.job_id
            """
        ),
        {"wf_id": workflow_id},
    )

    # Set all uninitialized to BLOCKED
    await session.execute(
        update(JobORM)
        .where(JobORM.workflow_id == workflow_id, JobORM.status == int(JobStatus.UNINITIALIZED))
        .values(status=int(JobStatus.BLOCKED))
    )

    # Set jobs with no dependencies to READY
    await session.execute(
        text(
            """
            UPDATE job SET status = :ready
            WHERE workflow_id = :wf_id AND status = :blocked
              AND id NOT IN (
                SELECT DISTINCT jdo.job_id FROM job_depends_on jdo
                WHERE jdo.workflow_id = :wf_id
              )
            """
        ),
        {
            "ready": int(JobStatus.READY),
            "wf_id": workflow_id,
            "blocked": int(JobStatus.BLOCKED),
        },
    )

    await session.commit()

    ready_row = (
        await session.execute(
            select(func.count())
            .select_from(JobORM)
            .where(JobORM.workflow_id == workflow_id, JobORM.status == int(JobStatus.READY))
        )
    ).scalar()

    blocked_row = (
        await session.execute(
            select(func.count())
            .select_from(JobORM)
            .where(JobORM.workflow_id == workflow_id, JobORM.status == int(JobStatus.BLOCKED))
        )
    ).scalar()

    return {
        "status": "initialized",
        "workflow_id": workflow_id,
        "ready_jobs": ready_row or 0,
        "blocked_jobs": blocked_row or 0,
    }


@router.post("/{workflow_id}/reset")
async def reset_workflow(workflow_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """Reset all jobs back to uninitialized and increment run_id."""
    stmt = select(WorkflowORM.id).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    await session.execute(
        update(JobORM)
        .where(JobORM.workflow_id == workflow_id)
        .values(status=int(JobStatus.UNINITIALIZED), attempt_id=0, unblocking_processed=1)
    )
    await session.execute(
        text(
            "UPDATE workflow_status SET run_id = run_id + 1, is_canceled = 0"
            " WHERE workflow_id = :wf_id"
        ),
        {"wf_id": workflow_id},
    )
    await session.commit()
    return {"status": "reset", "workflow_id": workflow_id}


@router.get("/{workflow_id}/status")
async def workflow_status(workflow_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """Get workflow status summary with job counts by status."""
    stmt = select(WorkflowORM.id).where(WorkflowORM.id == workflow_id)
    wf = (await session.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    counts = (
        await session.execute(
            select(JobORM.status, func.count())
            .where(JobORM.workflow_id == workflow_id)
            .group_by(JobORM.status)
        )
    ).all()

    status_counts = {JobStatus(row[0]).name.lower(): row[1] for row in counts}
    total = sum(row[1] for row in counts)

    ws = (
        await session.execute(
            select(WorkflowStatusORM).where(WorkflowStatusORM.workflow_id == workflow_id)
        )
    ).scalar_one_or_none()

    return {
        "workflow_id": workflow_id,
        "run_id": ws.run_id if ws else 0,
        "is_canceled": bool(ws.is_canceled) if ws else False,
        "total_jobs": total,
        "job_status_counts": status_counts,
    }
