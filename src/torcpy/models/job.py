"""Job models."""

from pydantic import BaseModel

from torcpy.models.enums import JobStatus


class JobListResponse(BaseModel):
    items: list["Job"]
    offset: int = 0
    limit: int = 10000
    has_more: bool = False


class JobCreate(BaseModel):
    workflow_id: int
    name: str
    command: str | None = None
    status: JobStatus = JobStatus.UNINITIALIZED
    resource_requirements_id: int | None = None
    scheduler_id: int | None = None
    failure_handler_id: int | None = None
    priority: int = 0
    cancel_on_blocking_job_failure: bool = True
    supports_termination: bool = False
    depends_on_job_ids: list[int] | None = None
    input_file_ids: list[int] | None = None
    output_file_ids: list[int] | None = None
    input_user_data_ids: list[int] | None = None
    output_user_data_ids: list[int] | None = None


class JobUpdate(BaseModel):
    name: str | None = None
    command: str | None = None
    status: JobStatus | None = None
    resource_requirements_id: int | None = None
    scheduler_id: int | None = None
    failure_handler_id: int | None = None
    priority: int | None = None
    cancel_on_blocking_job_failure: bool | None = None
    supports_termination: bool | None = None


class Job(BaseModel):
    id: int
    workflow_id: int
    name: str
    command: str | None = None
    status: JobStatus = JobStatus.UNINITIALIZED
    resource_requirements_id: int | None = None
    scheduler_id: int | None = None
    failure_handler_id: int | None = None
    attempt_id: int = 0
    priority: int = 0
    cancel_on_blocking_job_failure: bool = True
    supports_termination: bool = False
    unblocking_processed: int = 1
    depends_on_job_ids: list[int] = []
    input_file_ids: list[int] = []
    output_file_ids: list[int] = []
    input_user_data_ids: list[int] = []
    output_user_data_ids: list[int] = []
