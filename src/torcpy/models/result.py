"""Result models."""

from pydantic import BaseModel


class ResultCreate(BaseModel):
    workflow_id: int
    job_id: int
    run_id: int = 0
    compute_node_id: int | None = None
    return_code: int | None = None
    exec_time_minutes: float | None = None
    completion_time: float | None = None
    status: str | None = None
    peak_memory_bytes: int | None = None
    avg_memory_bytes: int | None = None
    peak_cpu_percent: float | None = None
    avg_cpu_percent: float | None = None


class Result(BaseModel):
    id: int
    workflow_id: int
    job_id: int
    run_id: int = 0
    compute_node_id: int | None = None
    return_code: int | None = None
    exec_time_minutes: float | None = None
    completion_time: float | None = None
    status: str | None = None
    peak_memory_bytes: int | None = None
    avg_memory_bytes: int | None = None
    peak_cpu_percent: float | None = None
    avg_cpu_percent: float | None = None
