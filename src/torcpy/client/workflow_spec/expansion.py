"""Parameter resolution, expansion helpers, and dependency level building."""

from __future__ import annotations

import re
from collections import deque
from typing import Callable, TypeVar

from torcpy.client.parameter_expansion import expand_parameters, substitute_template
from torcpy.client.workflow_spec.models import JobSpec


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


def _resolve_id(mapping: dict[str, int], name: str, kind: str, job_name: str) -> int:
    """Resolve a name to an ID, raising ValueError if not found."""
    if name not in mapping:
        raise ValueError(f"Job '{job_name}' references unknown {kind} '{name}'")
    return mapping[name]


def _resolve_ids(
    names: list[str], mapping: dict[str, int], kind: str, job_name: str
) -> list[int]:
    """Resolve a list of names to IDs."""
    return [_resolve_id(mapping, name, kind, job_name) for name in names]


T = TypeVar("T")


def _expand_parameterized(
    items: list[T],
    workflow_params: dict[str, str],
    factory: Callable[[T, dict[str, str]], T],
) -> list[T]:
    """Expand parameterized specs. Items without parameters pass through unchanged."""
    expanded: list[T] = []
    for item in items:
        effective = _resolve_parameters(
            item.parameters,  # type: ignore[attr-defined]
            item.use_parameters,  # type: ignore[attr-defined]
            workflow_params,
        )
        if effective:
            for params in expand_parameters(effective):
                expanded.append(factory(item, params))
        else:
            expanded.append(item)
    return expanded


def _expand_job_specs(
    jobs: list[JobSpec],
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
    all_names = {j.name for j in expanded}

    # Resolve depends_on_regexes
    for job in expanded:
        if job.depends_on_regexes:
            for pattern in job.depends_on_regexes:
                regex = re.compile(pattern)
                for name in all_names:
                    if regex.match(name) and name != job.name and name not in job.depends_on:
                        job.depends_on.append(name)

    return expanded


def _build_dependency_levels(jobs: list[JobSpec]) -> list[list[JobSpec]]:
    """Build dependency levels using Kahn's algorithm.

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
