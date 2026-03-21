"""Workflow creation functions and scheduler registry."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Callable

from torcpy.client.api_client import TorcClient
from torcpy.client.parameter_expansion import substitute_template
from torcpy.client.workflow_spec.expansion import (
    _build_dependency_levels,
    _expand_job_specs,
    _expand_parameterized,
    _resolve_id,
    _resolve_ids,
)
from torcpy.client.workflow_spec.models import (
    FailureHandlerSpec,
    FileSpec,
    ResourceRequirementsSpec,
    SchedulerSpec,
    UserDataSpec,
    WorkflowSpec,
)
from torcpy.models import (
    FailureHandlerCreate,
    FileCreate,
    LocalSchedulerCreate,
    ResourceRequirementsCreate,
    SlurmSchedulerCreate,
    UserDataCreate,
    WorkflowCreate,
)
from torcpy.models.enums import JobStatus

_JOB_STATUS_UNINITIALIZED = int(JobStatus.UNINITIALIZED)

logger = logging.getLogger(__name__)


# ── Scheduler registry ──


async def _make_local_scheduler(client: TorcClient, wf_id: int, spec: SchedulerSpec) -> int:
    ls = await client.create_local_scheduler(
        wf_id,
        LocalSchedulerCreate(workflow_id=wf_id, num_cpus=spec.num_cpus, memory=spec.memory),
    )
    return ls.id


async def _make_slurm_scheduler(client: TorcClient, wf_id: int, spec: SchedulerSpec) -> int:
    ss = await client.create_slurm_scheduler(
        wf_id,
        SlurmSchedulerCreate(
            workflow_id=wf_id,
            account=spec.account,
            partition=spec.partition,
            slurm_config=spec.slurm_config,
        ),
    )
    return ss.id


_SCHEDULER_CREATORS: dict[str, Callable] = {
    "local": _make_local_scheduler,
    "slurm": _make_slurm_scheduler,
}


# ── Creation helpers ──


async def _create_files(
    client: TorcClient,
    wf_id: int,
    files: list[FileSpec],
    parameters: dict[str, str],
) -> dict[str, int]:
    expanded = _expand_parameterized(
        files,
        parameters,
        lambda f, p: FileSpec(
            name=substitute_template(f.name, p),
            path=substitute_template(f.path, p) if f.path else None,
            st_mtime=f.st_mtime,
        ),
    )
    name_to_id: dict[str, int] = {}
    for f in expanded:
        created = await client.create_file(
            wf_id,
            FileCreate(workflow_id=wf_id, name=f.name, path=f.path, st_mtime=f.st_mtime),
        )
        name_to_id[f.name] = created.id
    return name_to_id


async def _create_user_data(
    client: TorcClient,
    wf_id: int,
    user_data: list[UserDataSpec],
    parameters: dict[str, str],
) -> dict[str, int]:
    expanded = _expand_parameterized(
        user_data,
        parameters,
        lambda ud, p: UserDataSpec(
            name=substitute_template(ud.name, p),
            data=ud.data,
            is_ephemeral=ud.is_ephemeral,
        ),
    )
    name_to_id: dict[str, int] = {}
    for ud in expanded:
        created = await client.create_user_data(
            wf_id,
            UserDataCreate(
                workflow_id=wf_id,
                name=ud.name,
                data=ud.data,
                is_ephemeral=ud.is_ephemeral,
            ),
        )
        name_to_id[ud.name] = created.id
    return name_to_id


async def _create_failure_handlers(
    client: TorcClient,
    wf_id: int,
    handlers: list[FailureHandlerSpec],
) -> dict[str, int]:
    name_to_id: dict[str, int] = {}
    for fh in handlers:
        created = await client.create_failure_handler(
            wf_id,
            FailureHandlerCreate(
                workflow_id=wf_id,
                name=fh.name,
                rules=fh.rules,
                default_max_retries=fh.default_max_retries,
                default_recovery_command=fh.default_recovery_command,
            ),
        )
        name_to_id[fh.name] = created.id
    return name_to_id


async def _create_resource_requirements(
    client: TorcClient,
    wf_id: int,
    rr_specs: list[ResourceRequirementsSpec],
) -> dict[str, int]:
    name_to_id: dict[str, int] = {}
    for rr_spec in rr_specs:
        created = await client.create_resource_requirements(
            wf_id,
            ResourceRequirementsCreate(
                workflow_id=wf_id,
                num_cpus=rr_spec.num_cpus,
                num_gpus=rr_spec.num_gpus,
                num_nodes=rr_spec.num_nodes,
                memory=rr_spec.memory,
                runtime=rr_spec.runtime,
            ),
        )
        if rr_spec.name:
            name_to_id[rr_spec.name] = created.id
    return name_to_id


async def _create_schedulers(
    client: TorcClient,
    wf_id: int,
    schedulers: list[SchedulerSpec],
) -> list[int]:
    ids: list[int] = []
    for s in schedulers:
        creator = _SCHEDULER_CREATORS.get(s.type)
        if creator is None:
            raise ValueError(
                f"Unknown scheduler type {s.type!r}. Known: {list(_SCHEDULER_CREATORS)}"
            )
        ids.append(await creator(client, wf_id, s))
    return ids


async def _create_jobs(
    client: TorcClient,
    wf_id: int,
    jobs_spec: list,
    parameters: dict[str, str],
    file_ids: dict[str, int],
    ud_ids: dict[str, int],
    rr_ids: dict[str, int],
    fh_ids: dict[str, int],
) -> dict[str, int]:
    _BATCH_SIZE = 50_000
    expanded_jobs = _expand_job_specs(jobs_spec, parameters)
    job_levels = _build_dependency_levels(expanded_jobs)

    job_name_to_id: dict[str, int] = {}
    total_created = 0
    for level in job_levels:
        level_creates: list[tuple[str, dict]] = []
        for job in level:
            rr_id: int | None = None
            if job.resource_requirements_name:
                rr_id = _resolve_id(
                    rr_ids, job.resource_requirements_name, "resource_requirements", job.name
                )
            elif job.resource_requirements:
                rr = job.resource_requirements
                created_rr = await client.create_resource_requirements(
                    wf_id,
                    ResourceRequirementsCreate(
                        workflow_id=wf_id,
                        num_cpus=rr.num_cpus,
                        num_gpus=rr.num_gpus,
                        num_nodes=rr.num_nodes,
                        memory=rr.memory,
                        runtime=rr.runtime,
                    ),
                )
                rr_id = created_rr.id

            fh_id: int | None = None
            if job.failure_handler:
                fh_id = _resolve_id(fh_ids, job.failure_handler, "failure_handler", job.name)

            dep_ids = _resolve_ids(job.depends_on, job_name_to_id, "job", job.name)
            input_file_ids = _resolve_ids(job.input_files, file_ids, "file", job.name)
            output_file_ids = _resolve_ids(job.output_files, file_ids, "file", job.name)
            input_ud_ids = _resolve_ids(job.input_user_data, ud_ids, "user_data", job.name)
            output_ud_ids = _resolve_ids(job.output_user_data, ud_ids, "user_data", job.name)

            job_dict: dict = {
                "workflow_id": wf_id,
                "name": job.name,
                "status": _JOB_STATUS_UNINITIALIZED,
                "priority": job.priority,
                "cancel_on_blocking_job_failure": job.cancel_on_blocking_job_failure,
                "supports_termination": job.supports_termination,
            }
            if job.command is not None:
                job_dict["command"] = job.command
            if rr_id is not None:
                job_dict["resource_requirements_id"] = rr_id
            if fh_id is not None:
                job_dict["failure_handler_id"] = fh_id
            if dep_ids:
                job_dict["depends_on_job_ids"] = dep_ids
            if input_file_ids:
                job_dict["input_file_ids"] = input_file_ids
            if output_file_ids:
                job_dict["output_file_ids"] = output_file_ids
            if input_ud_ids:
                job_dict["input_user_data_ids"] = input_ud_ids
            if output_ud_ids:
                job_dict["output_user_data_ids"] = output_ud_ids

            level_creates.append((job.name, job_dict))

        for offset in range(0, len(level_creates), _BATCH_SIZE):
            batch = level_creates[offset : offset + _BATCH_SIZE]
            returned_ids = await client.create_jobs([jd for _, jd in batch])
            for (name, _), job_id in zip(batch, returned_ids):
                job_name_to_id[name] = job_id
            total_created += len(batch)
            logger.info(
                "Created %d jobs for workflow_id=%d (%d/%d total)",
                len(batch),
                wf_id,
                total_created,
                len(expanded_jobs),
            )

    return job_name_to_id


# ── Coordinator ──


async def create_workflow_from_spec(
    client: TorcClient,
    spec: WorkflowSpec,
) -> int:
    """Create a complete workflow from a spec. Returns the workflow ID.

    Creates all components atomically: workflow, files, user_data, resource_requirements,
    failure_handlers, jobs (with dependencies), and schedulers.
    """
    user = spec.user or os.environ.get("USER") or os.environ.get("USERNAME") or "anonymous"

    wf = await client.create_workflow(
        WorkflowCreate(
            name=spec.name,
            user=user,
            metadata=spec.metadata,
            project=spec.project,
            slurm_defaults=spec.slurm_defaults,
            resource_monitor_config=spec.resource_monitor_config,
            execution_config=spec.execution_config,
        )
    )
    logger.info("Created workflow %d: %s", wf.id, spec.name)

    try:
        file_ids = await _create_files(client, wf.id, spec.files, spec.parameters)
        ud_ids = await _create_user_data(client, wf.id, spec.user_data, spec.parameters)
        fh_ids = await _create_failure_handlers(client, wf.id, spec.failure_handlers)
        rr_ids = await _create_resource_requirements(
            client, wf.id, spec.resource_requirements
        )
        await _create_schedulers(client, wf.id, spec.schedulers)
        expanded_jobs = await _create_jobs(
            client, wf.id, spec.jobs, spec.parameters, file_ids, ud_ids, rr_ids, fh_ids
        )
        logger.info(
            "Created %d files, %d user_data, %d jobs for workflow_id=%d",
            len(file_ids),
            len(ud_ids),
            len(expanded_jobs),
            wf.id,
        )
        logger.info("Workflow %d creation complete", wf.id)
    except Exception:
        logger.exception("Failed to create workflow components, deleting workflow %d", wf.id)
        with contextlib.suppress(Exception):
            await client.delete_workflow(wf.id)
        raise

    return wf.id
