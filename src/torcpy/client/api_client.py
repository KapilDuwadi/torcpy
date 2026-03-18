"""HTTP client for the TorcPy server API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from torcpy.models import (
    ComputeNode,
    ComputeNodeCreate,
    Event,
    EventCreate,
    FailureHandler,
    FailureHandlerCreate,
    File,
    FileCreate,
    Job,
    JobCreate,
    JobUpdate,
    LocalScheduler,
    LocalSchedulerCreate,
    ResourceRequirements,
    ResourceRequirementsCreate,
    Result,
    ResultCreate,
    SlurmScheduler,
    SlurmSchedulerCreate,
    UserData,
    UserDataCreate,
    Workflow,
    WorkflowCreate,
    WorkflowUpdate,
)
from torcpy.models.enums import ClaimJobsSortMethod

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8080/torcpy/v1"


class TorcClient:
    """Async HTTP client for the TorcPy REST API."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> TorcClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp,
            )

    # ── Health ──

    async def ping(self) -> dict:
        resp = await self._client.get("/ping")
        self._raise_for_status(resp)
        return resp.json()

    async def version(self) -> dict:
        resp = await self._client.get("/version")
        self._raise_for_status(resp)
        return resp.json()

    # ── Workflows ──

    async def create_workflow(self, body: WorkflowCreate) -> Workflow:
        resp = await self._client.post("/workflows", json=body.model_dump(exclude_none=True))
        self._raise_for_status(resp)
        return Workflow.model_validate(resp.json())

    async def list_workflows(self, offset: int = 0, limit: int = 10000) -> dict:
        resp = await self._client.get("/workflows", params={"offset": offset, "limit": limit})
        self._raise_for_status(resp)
        return resp.json()

    async def get_workflow(self, workflow_id: int) -> Workflow:
        resp = await self._client.get(f"/workflows/{workflow_id}")
        self._raise_for_status(resp)
        return Workflow.model_validate(resp.json())

    async def update_workflow(self, workflow_id: int, body: WorkflowUpdate) -> Workflow:
        resp = await self._client.patch(
            f"/workflows/{workflow_id}", json=body.model_dump(exclude_none=True)
        )
        self._raise_for_status(resp)
        return Workflow.model_validate(resp.json())

    async def delete_workflow(self, workflow_id: int) -> None:
        resp = await self._client.delete(f"/workflows/{workflow_id}")
        self._raise_for_status(resp)

    async def cancel_workflow(self, workflow_id: int) -> dict:
        resp = await self._client.post(f"/workflows/{workflow_id}/cancel")
        self._raise_for_status(resp)
        return resp.json()

    async def initialize_workflow(self, workflow_id: int) -> dict:
        resp = await self._client.post(f"/workflows/{workflow_id}/initialize")
        self._raise_for_status(resp)
        return resp.json()

    async def reset_workflow(self, workflow_id: int) -> dict:
        resp = await self._client.post(f"/workflows/{workflow_id}/reset")
        self._raise_for_status(resp)
        return resp.json()

    async def workflow_status(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/status")
        self._raise_for_status(resp)
        return resp.json()

    # ── Jobs ──

    async def create_job(self, workflow_id: int, body: JobCreate) -> Job:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/jobs", json=body.model_dump(exclude_none=True)
        )
        self._raise_for_status(resp)
        return Job.model_validate(resp.json())

    async def list_jobs(
        self,
        workflow_id: int,
        status: int | None = None,
        offset: int = 0,
        limit: int = 10000,
    ) -> dict:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if status is not None:
            params["status"] = status
        resp = await self._client.get(f"/workflows/{workflow_id}/jobs", params=params)
        self._raise_for_status(resp)
        return resp.json()

    async def get_job(self, workflow_id: int, job_id: int) -> Job:
        resp = await self._client.get(f"/workflows/{workflow_id}/jobs/{job_id}")
        self._raise_for_status(resp)
        return Job.model_validate(resp.json())

    async def update_job(self, workflow_id: int, job_id: int, body: JobUpdate) -> Job:
        resp = await self._client.patch(
            f"/workflows/{workflow_id}/jobs/{job_id}",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return Job.model_validate(resp.json())

    async def delete_job(self, workflow_id: int, job_id: int) -> None:
        resp = await self._client.delete(f"/workflows/{workflow_id}/jobs/{job_id}")
        self._raise_for_status(resp)

    async def claim_next_jobs(
        self,
        workflow_id: int,
        count: int = 1,
        compute_node_id: int | None = None,
        sort: ClaimJobsSortMethod = ClaimJobsSortMethod.PRIORITY,
    ) -> list[Job]:
        params: dict[str, Any] = {"count": count, "sort": sort.value}
        if compute_node_id is not None:
            params["compute_node_id"] = compute_node_id
        resp = await self._client.post(f"/workflows/{workflow_id}/jobs/claim", params=params)
        self._raise_for_status(resp)
        return [Job.model_validate(j) for j in resp.json()]

    async def complete_job(self, workflow_id: int, job_id: int, status: int = 5) -> Job:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/jobs/{job_id}/complete",
            params={"status": status},
        )
        self._raise_for_status(resp)
        return Job.model_validate(resp.json())

    async def reset_job(self, workflow_id: int, job_id: int) -> Job:
        resp = await self._client.post(f"/workflows/{workflow_id}/jobs/{job_id}/reset")
        self._raise_for_status(resp)
        return Job.model_validate(resp.json())

    # ── Files ──

    async def create_file(self, workflow_id: int, body: FileCreate) -> File:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/files", json=body.model_dump(exclude_none=True)
        )
        self._raise_for_status(resp)
        return File.model_validate(resp.json())

    async def list_files(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/files")
        self._raise_for_status(resp)
        return resp.json()

    async def get_file(self, workflow_id: int, file_id: int) -> File:
        resp = await self._client.get(f"/workflows/{workflow_id}/files/{file_id}")
        self._raise_for_status(resp)
        return File.model_validate(resp.json())

    async def delete_file(self, workflow_id: int, file_id: int) -> None:
        resp = await self._client.delete(f"/workflows/{workflow_id}/files/{file_id}")
        self._raise_for_status(resp)

    # ── User Data ──

    async def create_user_data(self, workflow_id: int, body: UserDataCreate) -> UserData:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/user_data",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return UserData.model_validate(resp.json())

    async def list_user_data(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/user_data")
        self._raise_for_status(resp)
        return resp.json()

    # ── Resource Requirements ──

    async def create_resource_requirements(
        self, workflow_id: int, body: ResourceRequirementsCreate
    ) -> ResourceRequirements:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/resource_requirements",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return ResourceRequirements.model_validate(resp.json())

    async def list_resource_requirements(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/resource_requirements")
        self._raise_for_status(resp)
        return resp.json()

    # ── Results ──

    async def create_result(self, workflow_id: int, body: ResultCreate) -> Result:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/results", json=body.model_dump(exclude_none=True)
        )
        self._raise_for_status(resp)
        return Result.model_validate(resp.json())

    async def list_results(self, workflow_id: int, job_id: int | None = None) -> dict:
        params = {}
        if job_id is not None:
            params["job_id"] = job_id
        resp = await self._client.get(f"/workflows/{workflow_id}/results", params=params)
        self._raise_for_status(resp)
        return resp.json()

    # ── Compute Nodes ──

    async def create_compute_node(self, workflow_id: int, body: ComputeNodeCreate) -> ComputeNode:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/compute_nodes",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return ComputeNode.model_validate(resp.json())

    async def list_compute_nodes(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/compute_nodes")
        self._raise_for_status(resp)
        return resp.json()

    # ── Events ──

    async def create_event(self, workflow_id: int, body: EventCreate) -> Event:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/events", json=body.model_dump(exclude_none=True)
        )
        self._raise_for_status(resp)
        return Event.model_validate(resp.json())

    async def list_events(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/events")
        self._raise_for_status(resp)
        return resp.json()

    # ── Failure Handlers ──

    async def create_failure_handler(
        self, workflow_id: int, body: FailureHandlerCreate
    ) -> FailureHandler:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/failure_handlers",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return FailureHandler.model_validate(resp.json())

    async def list_failure_handlers(self, workflow_id: int) -> dict:
        resp = await self._client.get(f"/workflows/{workflow_id}/failure_handlers")
        self._raise_for_status(resp)
        return resp.json()

    # ── Schedulers ──

    async def create_local_scheduler(
        self, workflow_id: int, body: LocalSchedulerCreate
    ) -> LocalScheduler:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/local_schedulers",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return LocalScheduler.model_validate(resp.json())

    async def create_slurm_scheduler(
        self, workflow_id: int, body: SlurmSchedulerCreate
    ) -> SlurmScheduler:
        resp = await self._client.post(
            f"/workflows/{workflow_id}/slurm_schedulers",
            json=body.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return SlurmScheduler.model_validate(resp.json())
