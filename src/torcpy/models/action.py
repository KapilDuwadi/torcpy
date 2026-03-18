"""Workflow action models."""

from pydantic import BaseModel

from torcpy.models.enums import ActionType, TriggerType


class WorkflowActionCreate(BaseModel):
    workflow_id: int
    trigger_type: TriggerType
    action_type: ActionType
    job_ids: list[int] | None = None
    job_name_regex: str | None = None
    commands: list[str] | None = None
    required_triggers: int = 1
    persistent: bool = False


class WorkflowAction(BaseModel):
    id: int
    workflow_id: int
    trigger_type: TriggerType
    action_type: ActionType
    job_ids: list[int] | None = None
    job_name_regex: str | None = None
    commands: list[str] | None = None
    trigger_count: int = 0
    required_triggers: int = 1
    executed: bool = False
    executed_at: float | None = None
    persistent: bool = False
