"""Tests for job API endpoints."""

import pytest
from httpx import AsyncClient


async def _create_workflow(client: AsyncClient) -> int:
    resp = await client.post("/workflows", json={"name": "job-test"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient):
    wf_id = await _create_workflow(client)
    resp = await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "job1", "command": "echo hello"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "job1"
    assert data["status"] == 0  # UNINITIALIZED


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient):
    wf_id = await _create_workflow(client)
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j1", "command": "echo 1"},
    )
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j2", "command": "echo 2"},
    )

    resp = await client.get(f"/workflows/{wf_id}/jobs")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_initialize_and_claim(client: AsyncClient):
    wf_id = await _create_workflow(client)

    # Create two independent jobs
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j1", "command": "echo 1"},
    )
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j2", "command": "echo 2"},
    )

    # Initialize
    init_resp = await client.post(f"/workflows/{wf_id}/initialize")
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["ready_jobs"] == 2

    # Claim jobs
    claim_resp = await client.post(
        f"/workflows/{wf_id}/jobs/claim", params={"count": 2}
    )
    assert claim_resp.status_code == 200
    claimed = claim_resp.json()
    assert len(claimed) == 2
    assert all(j["status"] == 3 for j in claimed)  # PENDING


@pytest.mark.asyncio
async def test_dependency_blocking(client: AsyncClient):
    wf_id = await _create_workflow(client)

    # Create job1
    j1_resp = await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j1", "command": "echo 1"},
    )
    j1_id = j1_resp.json()["id"]

    # Create job2 that depends on job1
    j2_resp = await client.post(
        f"/workflows/{wf_id}/jobs",
        json={
            "workflow_id": wf_id,
            "name": "j2",
            "command": "echo 2",
            "depends_on_job_ids": [j1_id],
        },
    )
    j2_id = j2_resp.json()["id"]

    # Initialize
    init_resp = await client.post(f"/workflows/{wf_id}/initialize")
    init_data = init_resp.json()
    assert init_data["ready_jobs"] == 1
    assert init_data["blocked_jobs"] == 1

    # Only job1 should be claimable
    claim_resp = await client.post(
        f"/workflows/{wf_id}/jobs/claim", params={"count": 10}
    )
    claimed = claim_resp.json()
    assert len(claimed) == 1
    assert claimed[0]["id"] == j1_id


@pytest.mark.asyncio
async def test_complete_job(client: AsyncClient):
    wf_id = await _create_workflow(client)

    j_resp = await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j1", "command": "echo 1"},
    )
    j_id = j_resp.json()["id"]

    await client.post(f"/workflows/{wf_id}/initialize")
    await client.post(f"/workflows/{wf_id}/jobs/claim", params={"count": 1})

    # Complete the job
    complete_resp = await client.post(
        f"/workflows/{wf_id}/jobs/{j_id}/complete", params={"status": 5}
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == 5  # COMPLETED


@pytest.mark.asyncio
async def test_reset_job(client: AsyncClient):
    wf_id = await _create_workflow(client)

    j_resp = await client.post(
        f"/workflows/{wf_id}/jobs",
        json={"workflow_id": wf_id, "name": "j1", "command": "echo 1", "status": 5},
    )
    j_id = j_resp.json()["id"]

    reset_resp = await client.post(f"/workflows/{wf_id}/jobs/{j_id}/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == 0  # UNINITIALIZED
