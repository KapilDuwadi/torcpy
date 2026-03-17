"""Scheduler models."""

from pydantic import BaseModel


class LocalSchedulerCreate(BaseModel):
    workflow_id: int
    num_cpus: int | None = None
    memory: str | None = None


class LocalScheduler(BaseModel):
    id: int
    workflow_id: int
    num_cpus: int | None = None
    memory: str | None = None


class SlurmSchedulerCreate(BaseModel):
    workflow_id: int
    account: str | None = None
    partition: str | None = None
    slurm_config: dict | None = None


class SlurmScheduler(BaseModel):
    id: int
    workflow_id: int
    account: str | None = None
    partition: str | None = None
    slurm_config: dict | None = None
