"""Workflow specification parsing and creation.

Supports JSON, JSON5, and YAML workflow definitions.
Handles parameter expansion, dependency resolution, and atomic workflow creation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from torcpy.client.api_client import TorcClient
from torcpy.client.parameter_expansion import expand_parameters, substitute_template
from torcpy.models import (
    FileCreate,
    JobCreate,
    LocalSchedulerCreate,
    ResourceRequirementsCreate,
    SlurmSchedulerCreate,
    UserDataCreate,
    WorkflowCreate,
    FailureHandlerCreate,
)
from torcpy.models.enums import JobStatus
from torcpy.models.failure_handler import FailureHandlerRule

logger = logging.getLogger(__name__)


class FileSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.path: str | None = data.get("path")
        self.st_mtime: float | None = data.get("st_mtime")
        self.parameters: dict[str, str] = data.get("parameters", {})


class UserDataSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.data: Any = data.get("data")
        self.is_ephemeral: bool = data.get("is_ephemeral", False)
        self.parameters: dict[str, str] = data.get("parameters", {})


class ResourceRequirementsSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.num_cpus: int | None = data.get("num_cpus")
        self.num_gpus: int | None = data.get("num_gpus")
        self.num_nodes: int | None = data.get("num_nodes")
        self.memory: str | None = data.get("memory")
        self.runtime: str | None = data.get("runtime")


class FailureHandlerSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.rules: list[dict[str, Any]] = data.get("rules", [])
        self.default_max_retries: int = data.get("default_max_retries", 0)
        self.default_recovery_command: str | None = data.get("default_recovery_command")


class JobSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.command: str | None = data.get("command")
        self.depends_on: list[str] = data.get("depends_on", [])
        self.depends_on_regexes: list[str] = data.get("depends_on_regexes", [])
        self.input_files: list[str] = data.get("input_files", [])
        self.output_files: list[str] = data.get("output_files", [])
        self.input_user_data: list[str] = data.get("input_user_data", [])
        self.output_user_data: list[str] = data.get("output_user_data", [])
        self.resource_requirements: ResourceRequirementsSpec | None = None
        self.failure_handler: str | None = data.get("failure_handler")
        self.priority: int = data.get("priority", 0)
        self.cancel_on_blocking_job_failure: bool = data.get(
            "cancel_on_blocking_job_failure", True
        )
        self.supports_termination: bool = data.get("supports_termination", False)
        self.parameters: dict[str, str] = data.get("parameters", {})
        self.parameter_mode: str = data.get("parameter_mode", "cartesian")

        rr = data.get("resource_requirements")
        if rr:
            self.resource_requirements = ResourceRequirementsSpec(rr)


class SchedulerSpec:
    def __init__(self, data: dict[str, Any]) -> None:
        self.type: str = data.get("type", "local")
        self.num_cpus: int | None = data.get("num_cpus")
        self.memory: str | None = data.get("memory")
        self.account: str | None = data.get("account")
        self.partition: str | None = data.get("partition")
        self.slurm_config: dict | None = data.get("slurm_config")


class WorkflowSpec:
    """Parsed workflow specification."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data.get("name", "unnamed")
        self.user: str | None = data.get("user")
        self.metadata: dict | None = data.get("metadata")
        self.project: str | None = data.get("project")
        self.slurm_defaults: dict | None = data.get("slurm_defaults")
        self.resource_monitor_config: dict | None = data.get("resource_monitor_config")
        self.execution_config: dict | None = data.get("execution_config")

        self.files: list[FileSpec] = [FileSpec(f) for f in data.get("files", [])]
        self.user_data: list[UserDataSpec] = [
            UserDataSpec(u) for u in data.get("user_data", [])
        ]
        self.jobs: list[JobSpec] = [JobSpec(j) for j in data.get("jobs", [])]
        self.schedulers: list[SchedulerSpec] = [
            SchedulerSpec(s) for s in data.get("schedulers", [])
        ]
        self.failure_handlers: list[FailureHandlerSpec] = [
            FailureHandlerSpec(fh) for fh in data.get("failure_handlers", [])
        ]

    @classmethod
    def from_file(cls, path: str | Path) -> WorkflowSpec:
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

        return cls(data)


def _expand_file_specs(files: list[FileSpec]) -> list[FileSpec]:
    """Expand parameterized file specs."""
    expanded: list[FileSpec] = []
    for f in files:
        if f.parameters:
            combos = expand_parameters(f.parameters)
            for params in combos:
                expanded.append(
                    FileSpec(
                        {
                            "name": substitute_template(f.name, params),
                            "path": substitute_template(f.path, params) if f.path else None,
                            "st_mtime": f.st_mtime,
                        }
                    )
                )
        else:
            expanded.append(f)
    return expanded


def _expand_user_data_specs(user_data: list[UserDataSpec]) -> list[UserDataSpec]:
    """Expand parameterized user data specs."""
    expanded: list[UserDataSpec] = []
    for ud in user_data:
        if ud.parameters:
            combos = expand_parameters(ud.parameters)
            for params in combos:
                expanded.append(
                    UserDataSpec(
                        {
                            "name": substitute_template(ud.name, params),
                            "data": ud.data,
                            "is_ephemeral": ud.is_ephemeral,
                        }
                    )
                )
        else:
            expanded.append(ud)
    return expanded


def _expand_job_specs(jobs: list[JobSpec], all_job_names: set[str]) -> list[JobSpec]:
    """Expand parameterized job specs and resolve regex dependencies."""
    expanded: list[JobSpec] = []
    for job in jobs:
        if job.parameters:
            combos = expand_parameters(job.parameters, mode=job.parameter_mode)
            for params in combos:
                new_data: dict[str, Any] = {
                    "name": substitute_template(job.name, params),
                    "command": (
                        substitute_template(job.command, params) if job.command else None
                    ),
                    "depends_on": [substitute_template(d, params) for d in job.depends_on],
                    "depends_on_regexes": job.depends_on_regexes,
                    "input_files": [substitute_template(f, params) for f in job.input_files],
                    "output_files": [substitute_template(f, params) for f in job.output_files],
                    "input_user_data": [
                        substitute_template(u, params) for u in job.input_user_data
                    ],
                    "output_user_data": [
                        substitute_template(u, params) for u in job.output_user_data
                    ],
                    "priority": job.priority,
                    "cancel_on_blocking_job_failure": job.cancel_on_blocking_job_failure,
                    "supports_termination": job.supports_termination,
                    "failure_handler": job.failure_handler,
                }
                if job.resource_requirements:
                    rr = job.resource_requirements
                    new_data["resource_requirements"] = {
                        "num_cpus": rr.num_cpus,
                        "num_gpus": rr.num_gpus,
                        "num_nodes": rr.num_nodes,
                        "memory": rr.memory,
                        "runtime": rr.runtime,
                    }
                expanded.append(JobSpec(new_data))
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
        expanded_files = _expand_file_specs(spec.files)
        file_name_to_id: dict[str, int] = {}
        for f in expanded_files:
            created = await client.create_file(
                wf_id,
                FileCreate(workflow_id=wf_id, name=f.name, path=f.path, st_mtime=f.st_mtime),
            )
            file_name_to_id[f.name] = created.id

        # 3. Create user data
        expanded_ud = _expand_user_data_specs(spec.user_data)
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
            rules = [
                FailureHandlerRule(**r) for r in fh.rules
            ]
            created_fh = await client.create_failure_handler(
                wf_id,
                FailureHandlerCreate(
                    workflow_id=wf_id,
                    name=fh.name,
                    rules=rules,
                    default_max_retries=fh.default_max_retries,
                    default_recovery_command=fh.default_recovery_command,
                ),
            )
            fh_name_to_id[fh.name] = created_fh.id

        # 5. Create schedulers
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

        # 6. Create jobs (expand parameters, resolve names to IDs)
        all_existing_names: set[str] = set()
        expanded_jobs = _expand_job_specs(spec.jobs, all_existing_names)

        # First pass: create all jobs without dependencies
        job_name_to_id: dict[str, int] = {}
        for job in expanded_jobs:
            rr_id = None
            if job.resource_requirements:
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

            fh_id = None
            if job.failure_handler and job.failure_handler in fh_name_to_id:
                fh_id = fh_name_to_id[job.failure_handler]

            created_job = await client.create_job(
                wf_id,
                JobCreate(
                    workflow_id=wf_id,
                    name=job.name,
                    command=job.command,
                    status=JobStatus.UNINITIALIZED,
                    resource_requirements_id=rr_id,
                    failure_handler_id=fh_id,
                    priority=job.priority,
                    cancel_on_blocking_job_failure=job.cancel_on_blocking_job_failure,
                    supports_termination=job.supports_termination,
                    input_file_ids=[
                        file_name_to_id[f]
                        for f in job.input_files
                        if f in file_name_to_id
                    ],
                    output_file_ids=[
                        file_name_to_id[f]
                        for f in job.output_files
                        if f in file_name_to_id
                    ],
                    input_user_data_ids=[
                        ud_name_to_id[u]
                        for u in job.input_user_data
                        if u in ud_name_to_id
                    ],
                    output_user_data_ids=[
                        ud_name_to_id[u]
                        for u in job.output_user_data
                        if u in ud_name_to_id
                    ],
                    depends_on_job_ids=[],  # Set in second pass
                ),
            )
            job_name_to_id[job.name] = created_job.id

        # Second pass: set explicit dependencies
        for job in expanded_jobs:
            if job.depends_on:
                dep_ids = [
                    job_name_to_id[dep]
                    for dep in job.depends_on
                    if dep in job_name_to_id
                ]
                if dep_ids:
                    job_id = job_name_to_id[job.name]
                    await client.update_job(
                        wf_id,
                        job_id,
                        body=type(
                            "Deps", (), {"model_dump": lambda self, **kw: {}}
                        )(),  # no-op; we need raw API call
                    )
                    # Use direct dependency insertion via a helper
                    # Since the API doesn't support adding deps via update,
                    # we recreate the job or use internal endpoint
                    # For now, create deps during job creation above
                    pass

        # Re-create jobs that have explicit dependencies properly
        # Actually, let's fix this: we need to create with deps
        for job in expanded_jobs:
            if job.depends_on:
                dep_ids = [
                    job_name_to_id[dep]
                    for dep in job.depends_on
                    if dep in job_name_to_id
                ]
                if dep_ids:
                    job_id = job_name_to_id[job.name]
                    # Delete and recreate with dependencies
                    await client.delete_job(wf_id, job_id)

                    rr_id = None
                    if job.resource_requirements:
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

                    fh_id = None
                    if job.failure_handler and job.failure_handler in fh_name_to_id:
                        fh_id = fh_name_to_id[job.failure_handler]

                    created_job = await client.create_job(
                        wf_id,
                        JobCreate(
                            workflow_id=wf_id,
                            name=job.name,
                            command=job.command,
                            status=JobStatus.UNINITIALIZED,
                            resource_requirements_id=rr_id,
                            failure_handler_id=fh_id,
                            priority=job.priority,
                            cancel_on_blocking_job_failure=job.cancel_on_blocking_job_failure,
                            supports_termination=job.supports_termination,
                            depends_on_job_ids=dep_ids,
                            input_file_ids=[
                                file_name_to_id[f]
                                for f in job.input_files
                                if f in file_name_to_id
                            ],
                            output_file_ids=[
                                file_name_to_id[f]
                                for f in job.output_files
                                if f in file_name_to_id
                            ],
                            input_user_data_ids=[
                                ud_name_to_id[u]
                                for u in job.input_user_data
                                if u in ud_name_to_id
                            ],
                            output_user_data_ids=[
                                ud_name_to_id[u]
                                for u in job.output_user_data
                                if u in ud_name_to_id
                            ],
                        ),
                    )
                    job_name_to_id[job.name] = created_job.id

        logger.info(
            "Created %d files, %d user_data, %d jobs for workflow %d",
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
