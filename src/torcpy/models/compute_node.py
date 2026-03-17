"""Compute node models."""

from pydantic import BaseModel


class ComputeNodeCreate(BaseModel):
    workflow_id: int
    hostname: str
    pid: int | None = None
    start_time: float | None = None
    is_active: bool = True
    num_cpus: int | None = None
    memory_gb: float | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    time_limit: float | None = None
    scheduler_config_id: int | None = None


class ComputeNodeUpdate(BaseModel):
    hostname: str | None = None
    is_active: bool | None = None
    num_cpus: int | None = None
    memory_gb: float | None = None
    num_gpus: int | None = None


class ComputeNode(BaseModel):
    id: int
    workflow_id: int
    hostname: str
    pid: int | None = None
    start_time: float | None = None
    is_active: bool = True
    num_cpus: int | None = None
    memory_gb: float | None = None
    num_gpus: int | None = None
    num_nodes: int | None = None
    time_limit: float | None = None
    scheduler_config_id: int | None = None
