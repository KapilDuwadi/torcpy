"""Workflow models."""

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    name: str
    user: str | None = None
    metadata: dict | None = None
    slurm_defaults: dict | None = None
    resource_monitor_config: dict | None = None
    execution_config: dict | None = None
    use_pending_failed: bool = False
    project: str | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = None
    metadata: dict | None = None
    slurm_defaults: dict | None = None
    resource_monitor_config: dict | None = None
    execution_config: dict | None = None
    use_pending_failed: bool | None = None
    project: str | None = None


class WorkflowStatus(BaseModel):
    workflow_id: int
    run_id: int = 0
    is_archived: bool = False
    is_canceled: bool = False


class Workflow(BaseModel):
    id: int
    name: str
    user: str | None = None
    timestamp: float | None = None
    status: WorkflowStatus | None = None
    metadata: dict | None = None
    slurm_defaults: dict | None = None
    resource_monitor_config: dict | None = None
    execution_config: dict | None = None
    use_pending_failed: bool = False
    project: str | None = None
    job_count: int = Field(default=0, description="Total number of jobs in workflow")
