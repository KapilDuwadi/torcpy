"""Job API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.enums import ClaimJobsSortMethod, JobStatus
from torcpy.models.job import Job, JobCreate, JobUpdate
from torcpy.server.database import clamp_pagination, write_transaction
from torcpy.server.deps import get_session
from torcpy.server.orm import (
    JobDependsOnORM,
    JobInputFileORM,
    JobInputUserDataORM,
    JobORM,
    JobOutputFileORM,
    JobOutputUserDataORM,
    WorkflowORM,
)

router = APIRouter(prefix="/workflows/{workflow_id}/jobs", tags=["jobs"])


def _orm_to_job(obj: JobORM) -> Job:
    return Job(
        id=obj.id,
        workflow_id=obj.workflow_id,
        name=obj.name,
        command=obj.command,
        status=JobStatus(obj.status),
        resource_requirements_id=obj.resource_requirements_id,
        scheduler_id=obj.scheduler_id,
        failure_handler_id=obj.failure_handler_id,
        attempt_id=obj.attempt_id,
        priority=obj.priority,
        unblocking_processed=obj.unblocking_processed,
        cancel_on_blocking_job_failure=bool(obj.cancel_on_blocking_job_failure),
        supports_termination=bool(obj.supports_termination),
        depends_on_job_ids=[lnk.depends_on_job_id for lnk in obj.depends_on_links],
        input_file_ids=[lnk.file_id for lnk in obj.input_file_links],
        output_file_ids=[lnk.file_id for lnk in obj.output_file_links],
        input_user_data_ids=[lnk.user_data_id for lnk in obj.input_user_data_links],
        output_user_data_ids=[lnk.user_data_id for lnk in obj.output_user_data_links],
    )


@router.post("", status_code=201)
async def create_job(
    workflow_id: int, body: JobCreate, session: AsyncSession = Depends(get_session)
) -> Job:
    wf = (
        await session.execute(select(WorkflowORM.id).where(WorkflowORM.id == workflow_id))
    ).scalar_one_or_none()
    if wf is None:
        raise HTTPException(404, f"Workflow {workflow_id} not found")

    obj = JobORM(
        workflow_id=workflow_id,
        name=body.name,
        command=body.command,
        status=int(body.status),
        resource_requirements_id=body.resource_requirements_id,
        scheduler_id=body.scheduler_id,
        failure_handler_id=body.failure_handler_id,
        priority=body.priority,
        cancel_on_blocking_job_failure=int(body.cancel_on_blocking_job_failure),
        supports_termination=int(body.supports_termination),
    )
    session.add(obj)
    await session.flush()  # get obj.id

    if body.depends_on_job_ids:
        for dep_id in body.depends_on_job_ids:
            session.add(
                JobDependsOnORM(job_id=obj.id, depends_on_job_id=dep_id, workflow_id=workflow_id)
            )
    if body.input_file_ids:
        for fid in body.input_file_ids:
            session.add(JobInputFileORM(job_id=obj.id, file_id=fid, workflow_id=workflow_id))
    if body.output_file_ids:
        for fid in body.output_file_ids:
            session.add(JobOutputFileORM(job_id=obj.id, file_id=fid, workflow_id=workflow_id))
    if body.input_user_data_ids:
        for uid in body.input_user_data_ids:
            session.add(JobInputUserDataORM(job_id=obj.id, user_data_id=uid))
    if body.output_user_data_ids:
        for uid in body.output_user_data_ids:
            session.add(JobOutputUserDataORM(job_id=obj.id, user_data_id=uid))

    await session.commit()

    # Re-fetch with relationships loaded
    result = await session.execute(select(JobORM).where(JobORM.id == obj.id))
    job_obj = result.scalar_one()
    return _orm_to_job(job_obj)


@router.get("")
async def list_jobs(
    workflow_id: int,
    status: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = select(JobORM).where(JobORM.workflow_id == workflow_id)
    if status is not None:
        stmt = stmt.where(JobORM.status == status)
    stmt = stmt.order_by(JobORM.id).offset(off).limit(lim + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().unique().all())
    has_more = len(rows) > lim
    items = [_orm_to_job(r) for r in rows[:lim]]
    return {"items": items, "offset": off, "limit": lim, "has_more": has_more}


@router.get("/{job_id}")
async def get_job(
    workflow_id: int, job_id: int, session: AsyncSession = Depends(get_session)
) -> Job:
    stmt = select(JobORM).where(JobORM.id == job_id, JobORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return _orm_to_job(obj)


@router.patch("/{job_id}")
async def update_job(
    workflow_id: int,
    job_id: int,
    body: JobUpdate,
    session: AsyncSession = Depends(get_session),
) -> Job:
    stmt = select(JobORM).where(JobORM.id == job_id, JobORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Job {job_id} not found")

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
            setattr(obj, field, val)
    if body.status is not None:
        obj.status = int(body.status)
    if body.cancel_on_blocking_job_failure is not None:
        obj.cancel_on_blocking_job_failure = int(body.cancel_on_blocking_job_failure)
    if body.supports_termination is not None:
        obj.supports_termination = int(body.supports_termination)

    await session.commit()
    await session.refresh(obj)
    return _orm_to_job(obj)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    workflow_id: int, job_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(JobORM).where(JobORM.id == job_id, JobORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Job {job_id} not found")
    await session.delete(obj)
    await session.commit()


@router.post("/claim")
async def claim_next_jobs(
    workflow_id: int,
    request: Request,
    count: int = Query(1, ge=1, le=100),
    compute_node_id: int | None = None,
    sort: ClaimJobsSortMethod = ClaimJobsSortMethod.PRIORITY,
    session: AsyncSession = Depends(get_session),
) -> list[Job]:
    """Claim the next available jobs using a write lock to prevent double-allocation."""
    order_clause = "j.priority DESC, j.id ASC"
    if sort == ClaimJobsSortMethod.GPUS_RUNTIME_MEMORY:
        order_clause = (
            "COALESCE(rr.num_gpus, 0) DESC, "
            "COALESCE(rr.runtime_s, 0) DESC, "
            "COALESCE(rr.memory_bytes, 0) DESC, "
            "j.id ASC"
        )
    elif sort == ClaimJobsSortMethod.CPUS_RUNTIME_MEMORY:
        order_clause = (
            "COALESCE(rr.num_cpus, 0) DESC, "
            "COALESCE(rr.runtime_s, 0) DESC, "
            "COALESCE(rr.memory_bytes, 0) DESC, "
            "j.id ASC"
        )

    async with write_transaction(session):
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT j.id FROM job j
                    LEFT JOIN resource_requirements rr ON rr.id = j.resource_requirements_id
                    WHERE j.workflow_id = :wf_id AND j.status = :status
                    ORDER BY {order_clause}
                    LIMIT :cnt
                    """
                ),
                {"wf_id": workflow_id, "status": int(JobStatus.READY), "cnt": count},
            )
        ).all()

        if not rows:
            return []

        job_ids = [r[0] for r in rows]
        placeholders = ",".join(str(jid) for jid in job_ids)
        await session.execute(
            text(f"UPDATE job SET status = :status WHERE id IN ({placeholders})"),
            {"status": int(JobStatus.PENDING)},
        )

        if compute_node_id is not None:
            for jid in job_ids:
                await session.execute(
                    text(
                        "INSERT OR REPLACE INTO job_internal"
                        " (job_id, active_compute_node_id) VALUES (:jid, :cn_id)"
                    ),
                    {"jid": jid, "cn_id": compute_node_id},
                )

    # Re-fetch with relationships
    result_list = []
    for jid in job_ids:
        obj = (await session.execute(select(JobORM).where(JobORM.id == jid))).scalar_one_or_none()
        if obj:
            result_list.append(_orm_to_job(obj))
    return result_list


@router.post("/{job_id}/complete")
async def complete_job(
    workflow_id: int,
    job_id: int,
    request: Request,
    status: int = Query(..., ge=5, le=10),
    session: AsyncSession = Depends(get_session),
) -> Job:
    """Complete a job and signal the background unblock task."""
    stmt = select(JobORM).where(JobORM.id == job_id, JobORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Job {job_id} not found")

    obj.status = status
    obj.unblocking_processed = 0
    await session.commit()

    bg_task = getattr(request.app.state, "bg_unblock", None)
    if bg_task:
        bg_task.signal()

    await session.refresh(obj)
    return _orm_to_job(obj)


@router.post("/{job_id}/reset")
async def reset_job(
    workflow_id: int,
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> Job:
    """Reset a job back to uninitialized."""
    stmt = select(JobORM).where(JobORM.id == job_id, JobORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"Job {job_id} not found")

    obj.status = int(JobStatus.UNINITIALIZED)
    obj.attempt_id = 0
    obj.unblocking_processed = 1
    await session.commit()
    await session.refresh(obj)
    return _orm_to_job(obj)
