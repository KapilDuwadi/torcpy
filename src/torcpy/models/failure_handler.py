"""Failure handler models."""

from pydantic import BaseModel


class FailureHandlerRule(BaseModel):
    exit_codes: list[int] | None = None
    exit_code_ranges: list[list[int]] | None = None
    recovery_command: str | None = None
    max_retries: int = 0


class FailureHandlerCreate(BaseModel):
    workflow_id: int
    name: str
    rules: list[FailureHandlerRule] = []
    default_max_retries: int = 0
    default_recovery_command: str | None = None


class FailureHandler(BaseModel):
    id: int
    workflow_id: int
    name: str
    rules: list[FailureHandlerRule] = []
    default_max_retries: int = 0
    default_recovery_command: str | None = None
