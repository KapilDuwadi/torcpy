"""Workflow specification parsing and creation.

Supports JSON, JSON5, and YAML workflow definitions.
Handles parameter expansion, dependency resolution, and atomic workflow creation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import deque
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from torcpy.client.api_client import TorcClient
from torcpy.client.parameter_expansion import expand_parameters, substitute_template
from torcpy.models import (
    FailureHandlerCreate,
    FileCreate,
    JobCreate,
    LocalSchedulerCreate,
    ResourceRequirementsCreate,
    SlurmSchedulerCreate,
    UserDataCreate,
    WorkflowCreate,
)
from torcpy.models.enums import JobStatus

_JOB_STATUS_UNINITIALIZED = int(JobStatus.UNINITIALIZED)
from torcpy.models.failure_handler import FailureHandlerRule

logger = logging.getLogger(__name__)


class FileSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    path: str | None = None
    st_mtime: float | None = None
    parameters: dict[str, str] = {}
    use_parameters: list[str] | None = None


class UserDataSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    data: Any = None
    is_ephemeral: bool = False
    parameters: dict[str, str] = {}
    use_parameters: list[str] | None = None


class ResourceRequirementsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    num_cpus: int | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    memory: str | None = None
    runtime: str | None = None


class FailureHandlerSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    rules: list[FailureHandlerRule] = []
    default_max_retries: int = 0
    default_recovery_command: str | None = None


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    command: str | None = None
    depends_on: list[str] = []
    depends_on_regexes: list[str] = []
    input_files: list[str] = []
    output_files: list[str] = []
    input_user_data: list[str] = []
    output_user_data: list[str] = []
    resource_requirements: ResourceRequirementsSpec | None = None
    resource_requirements_name: str | None = None
    failure_handler: str | None = None
    priority: int = 0
    cancel_on_blocking_job_failure: bool = True
    supports_termination: bool = False
    parameters: dict[str, str] = {}
    use_parameters: list[str] | None = None
    parameter_mode: str = "cartesian"

    @model_validator(mode="before")
    @classmethod
    def _split_resource_requirements(cls, data: Any) -> Any:
        if isinstance(data, dict):
            rr = data.get("resource_requirements")
            if isinstance(rr, str):
                data = {**data, "resource_requirements": None, "resource_requirements_name": rr}
        return data


class SchedulerSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = "local"
    num_cpus: int | None = None
    memory: str | None = None
    account: str | None = None
    partition: str | None = None
    slurm_config: dict | None = None


class WorkflowSpec(BaseModel):
    """Parsed workflow specification."""

    model_config = ConfigDict(extra="ignore")
    name: str = "unnamed"
    user: str | None = None
    metadata: dict | None = None
    project: str | None = None
    slurm_defaults: dict | None = None
    resource_monitor_config: dict | None = None
    execution_config: dict | None = None
    parameters: dict[str, str] = {}
    resource_requirements: list[ResourceRequirementsSpec] = []
    files: list[FileSpec] = []
    user_data: list[UserDataSpec] = []
    jobs: list[JobSpec] = []
    schedulers: list[SchedulerSpec] = []
    failure_handlers: list[FailureHandlerSpec] = []

    @model_validator(mode="after")
    def _validate_rr_refs(self) -> "WorkflowSpec":
        rr_names = {rr.name for rr in self.resource_requirements}
        for job in self.jobs:
            if job.resource_requirements_name and job.resource_requirements_name not in rr_names:
                raise ValueError(
                    f"Job '{job.name}' references unknown resource_requirements"
                    f" '{job.resource_requirements_name}'"
                )
        return self

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkflowSpec":
        """Load a workflow spec from a file (JSON, JSON5, or YAML)."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text)
        elif suffix == ".json5":
            try:
                import json5 as j5

                data = j5.loads(text)
            except ImportError:
                raise ImportError("json5 package required for .json5 files")
        else:
            data = json.loads(text)

        return cls.model_validate(data)


def _resolve_parameters(
    local_params: dict[str, str],
    use_params: list[str] | None,
    workflow_params: dict[str, str],
) -> dict[str, str]:
    """Resolve effective parameters for a job or file.

    Priority (matching Rust WorkflowSpec::resolve_parameters):
    - If local_params non-empty → use them (they override workflow-level)
    - Else if use_params set → filter workflow_params to only those names
    - Else → empty dict (not parameterized)
    """
    if local_params:
        return local_params
    if use_params is not None:
        return {k: v for k, v in workflow_params.items() if k in use_params}
    return {}


def _expand_file_specs(
    files: list[FileSpec],
    workflow_params: dict[str, str] | None = None,
) -> list[FileSpec]:
    """Expand parameterized file specs."""
    if workflow_params is None:
        workflow_params = {}
    expanded: list[FileSpec] = []
    for f in files:
        effective_params = _resolve_parameters(f.parameters, f.use_parameters, workflow_params)
        if effective_params:
            combos = expand_parameters(effective_params)
            for params in combos:
                expanded.append(
                    FileSpec(
                        name=substitute_template(f.name, params),
                        path=substitute_template(f.path, params) if f.path else None,
                        st_mtime=f.st_mtime,
                    )
                )
        else:
            expanded.append(f)
    return expanded


def _expand_user_data_specs(
    user_data: list[UserDataSpec],
    workflow_params: dict[str, str] | None = None,
) -> list[UserDataSpec]:
    """Expand parameterized user data specs."""
    if workflow_params is None:
        workflow_params = {}
    expanded: list[UserDataSpec] = []
    for ud in user_data:
        effective_params = _resolve_parameters(ud.parameters, ud.use_parameters, workflow_params)
        if effective_params:
            combos = expand_parameters(effective_params)
            for params in combos:
                expanded.append(
                    UserDataSpec(
                        name=substitute_template(ud.name, params),
                        data=ud.data,
                        is_ephemeral=ud.is_ephemeral,
                    )
                )
        else:
            expanded.append(ud)
    return expanded


def _expand_job_specs(
    jobs: list[JobSpec],
    all_job_names: set[str],
    workflow_params: dict[str, str] | None = None,
) -> list[JobSpec]:
    """Expand parameterized job specs and resolve regex dependencies."""
    if workflow_params is None:
        workflow_params = {}
    expanded: list[JobSpec] = []
    for job in jobs:
        effective_params = _resolve_parameters(job.parameters, job.use_parameters, workflow_params)
        if effective_params:
            combos = expand_parameters(effective_params, mode=job.parameter_mode)
            for params in combos:
                expanded.append(
                    JobSpec(
                        name=substitute_template(job.name, params),
                        command=(
                            substitute_template(job.command, params) if job.command else None
                        ),
                        depends_on=[substitute_template(d, params) for d in job.depends_on],
                        depends_on_regexes=job.depends_on_regexes,
                        input_files=[
                            substitute_template(f, params) for f in job.input_files
                        ],
                        output_files=[
                            substitute_template(f, params) for f in job.output_files
                        ],
                        input_user_data=[
                            substitute_template(u, params) for u in job.input_user_data
                        ],
                        output_user_data=[
                            substitute_template(u, params) for u in job.output_user_data
                        ],
                        priority=job.priority,
                        cancel_on_blocking_job_failure=job.cancel_on_blocking_job_failure,
                        supports_termination=job.supports_termination,
                        failure_handler=job.failure_handler,
                        resource_requirements=job.resource_requirements,
                        resource_requirements_name=job.resource_requirements_name,
                    )
                )
        else:
            expanded.append(job)

    # Collect all final job names for regex resolution
    all_names = all_job_names | {j.name for j in expanded}

    # Resolve depends_on_regexes
    for job in expanded:
        if job.depends_on_regexes:
            for pattern in job.depends_on_regexes:
                regex = re.compile(pattern)
                for name in all_names:
                    if regex.match(name) and name != job.name and name not in job.depends_on:
                        job.depends_on.append(name)

    return expanded


def _topological_sort_jobs(jobs: list[JobSpec]) -> list[list[JobSpec]]:
    """Sort jobs into dependency levels using Kahn's algorithm.

    Returns a list of levels where level 0 has no deps and each subsequent
    level's deps are all in earlier levels. Raises ValueError on unknown deps
    or circular dependencies.
    """
    name_to_job: dict[str, JobSpec] = {j.name: j for j in jobs}
    in_degree: dict[str, int] = {j.name: 0 for j in jobs}
    dependents: dict[str, list[str]] = {j.name: [] for j in jobs}

    for job in jobs:
        for dep in job.depends_on:
            if dep not in name_to_job:
                raise ValueError(f"Job '{job.name}' depends on unknown job '{dep}'")
            in_degree[job.name] += 1
            dependents[dep].append(job.name)

    levels: list[list[JobSpec]] = []
    queue: deque[JobSpec] = deque(j for j in jobs if in_degree[j.name] == 0)

    while queue:
        level = list(queue)
        levels.append(level)
        queue.clear()
        for job in level:
            for dep_name in dependents[job.name]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    queue.append(name_to_job[dep_name])

    total_processed = sum(len(lvl) for lvl in levels)
    if total_processed != len(jobs):
        raise ValueError("Circular dependency detected in job graph")

    return levels


def _resolve_id(mapping: dict[str, int], name: str, kind: str, job_name: str) -> int:
    """Resolve a name to an ID, raising ValueError if not found."""
    if name not in mapping:
        raise ValueError(f"Job '{job_name}' references unknown {kind} '{name}'")
    return mapping[name]


async def create_workflow_from_spec(
    client: TorcClient,
    spec: WorkflowSpec,
) -> int:
    """Create a complete workflow from a spec. Returns the workflow ID.

    Creates all components atomically: workflow, files, user_data, resource_requirements,
    failure_handlers, jobs (with dependencies), and schedulers.
    """
    user = spec.user or os.environ.get("USER") or os.environ.get("USERNAME") or "anonymous"

    # 1. Create workflow
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
    wf_id = wf.id
    logger.info("Created workflow %d: %s", wf_id, spec.name)

    try:
        # 2. Create files (expand parameters first)
        expanded_files = _expand_file_specs(spec.files, spec.parameters)
        file_name_to_id: dict[str, int] = {}
        for f in expanded_files:
            created = await client.create_file(
                wf_id,
                FileCreate(workflow_id=wf_id, name=f.name, path=f.path, st_mtime=f.st_mtime),
            )
            file_name_to_id[f.name] = created.id

        # 3. Create user data
        expanded_ud = _expand_user_data_specs(spec.user_data, spec.parameters)
        ud_name_to_id: dict[str, int] = {}
        for ud in expanded_ud:
            created_ud = await client.create_user_data(
                wf_id,
                UserDataCreate(
                    workflow_id=wf_id,
                    name=ud.name,
                    data=ud.data,
                    is_ephemeral=ud.is_ephemeral,
                ),
            )
            ud_name_to_id[ud.name] = created_ud.id

        # 4. Create failure handlers
        fh_name_to_id: dict[str, int] = {}
        for fh in spec.failure_handlers:
            created_fh = await client.create_failure_handler(
                wf_id,
                FailureHandlerCreate(
                    workflow_id=wf_id,
                    name=fh.name,
                    rules=fh.rules,
                    default_max_retries=fh.default_max_retries,
                    default_recovery_command=fh.default_recovery_command,
                ),
            )
            fh_name_to_id[fh.name] = created_fh.id

        # 5. Create named resource requirements once (shared across jobs)
        rr_name_to_id: dict[str, int] = {}
        for rr_spec in spec.resource_requirements:
            created_rr = await client.create_resource_requirements(
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
                rr_name_to_id[rr_spec.name] = created_rr.id

        # 6. Create schedulers
        scheduler_ids: list[int] = []
        for s in spec.schedulers:
            if s.type == "slurm":
                ss = await client.create_slurm_scheduler(
                    wf_id,
                    SlurmSchedulerCreate(
                        workflow_id=wf_id,
                        account=s.account,
                        partition=s.partition,
                        slurm_config=s.slurm_config,
                    ),
                )
                scheduler_ids.append(ss.id)
            else:
                ls = await client.create_local_scheduler(
                    wf_id,
                    LocalSchedulerCreate(
                        workflow_id=wf_id,
                        num_cpus=s.num_cpus,
                        memory=s.memory,
                    ),
                )
                scheduler_ids.append(ls.id)

        # 7. Expand and topologically sort jobs, then create in dependency order
        _BATCH_SIZE = 50_000
        all_existing_names: set[str] = set()
        expanded_jobs = _expand_job_specs(spec.jobs, all_existing_names, spec.parameters)
        job_levels = _topological_sort_jobs(expanded_jobs)

        job_name_to_id: dict[str, int] = {}
        total_created = 0
        for level in job_levels:
            # Build (name, job_dict) pairs — plain dicts bypass Pydantic construction
            # and model_dump overhead for 300k+ jobs.
            # Inline resource requirements are created individually first (unusual but valid).
            level_creates: list[tuple[str, dict]] = []
            for job in level:
                rr_id: int | None = None
                if job.resource_requirements_name:
                    rr_id = _resolve_id(
                        rr_name_to_id, job.resource_requirements_name, "resource_requirements",
                        job.name,
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
                    fh_id = _resolve_id(
                        fh_name_to_id, job.failure_handler, "failure_handler", job.name
                    )

                dep_ids = [
                    _resolve_id(job_name_to_id, dep, "job", job.name)
                    for dep in job.depends_on
                ]
                input_file_ids = [
                    _resolve_id(file_name_to_id, f, "file", job.name)
                    for f in job.input_files
                ]
                output_file_ids = [
                    _resolve_id(file_name_to_id, f, "file", job.name)
                    for f in job.output_files
                ]
                input_ud_ids = [
                    _resolve_id(ud_name_to_id, u, "user_data", job.name)
                    for u in job.input_user_data
                ]
                output_ud_ids = [
                    _resolve_id(ud_name_to_id, u, "user_data", job.name)
                    for u in job.output_user_data
                ]

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

            # Send in batches of 50,000
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

        logger.info(
            "Created %d files, %d user_data, %d jobs for workflow_id=%d",
            len(expanded_files),
            len(expanded_ud),
            len(expanded_jobs),
            wf_id,
        )

    except Exception:
        logger.exception("Failed to create workflow components, deleting workflow %d", wf_id)
        try:
            await client.delete_workflow(wf_id)
        except Exception:
            pass
        raise

    return wf_id
