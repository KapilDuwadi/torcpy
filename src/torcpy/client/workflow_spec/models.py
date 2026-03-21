"""Workflow specification Pydantic models and file format loader registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from torcpy.models.failure_handler import FailureHandlerRule


def _load_json5(text: str) -> dict:
    try:
        import json5 as j5

        return j5.loads(text)
    except ImportError:
        raise ImportError("json5 package required for .json5 files")


_FORMAT_LOADERS: dict[str, Callable[[str], dict]] = {
    ".yaml": yaml.safe_load,
    ".yml": yaml.safe_load,
    ".json": json.loads,
    ".json5": _load_json5,
}


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
        loader = _FORMAT_LOADERS.get(path.suffix.lower())
        if loader is None:
            supported = ", ".join(_FORMAT_LOADERS)
            raise ValueError(
                f"Unsupported format {path.suffix!r}. Supported: {supported}"
            )
        return cls.model_validate(loader(path.read_text(encoding="utf-8")))
