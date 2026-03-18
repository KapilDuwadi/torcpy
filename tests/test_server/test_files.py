"""Tests for file API endpoints."""

import pytest
from httpx import AsyncClient


async def _create_workflow(client: AsyncClient) -> int:
    resp = await client.post("/workflows", json={"name": "file-test"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_and_list_files(client: AsyncClient):
    wf_id = await _create_workflow(client)

    resp = await client.post(
        f"/workflows/{wf_id}/files",
        json={"workflow_id": wf_id, "name": "input.txt", "path": "/data/input.txt"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "input.txt"

    list_resp = await client.get(f"/workflows/{wf_id}/files")
    assert len(list_resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_implicit_dependency_via_files(client: AsyncClient):
    """Test that implicit deps are created when jobs share files."""
    wf_id = await _create_workflow(client)

    # Create a file
    file_resp = await client.post(
        f"/workflows/{wf_id}/files",
        json={"workflow_id": wf_id, "name": "data.csv"},
    )
    file_id = file_resp.json()["id"]

    # Job1 produces the file
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={
            "workflow_id": wf_id,
            "name": "producer",
            "command": "echo produce",
            "output_file_ids": [file_id],
        },
    )

    # Job2 consumes the file
    await client.post(
        f"/workflows/{wf_id}/jobs",
        json={
            "workflow_id": wf_id,
            "name": "consumer",
            "command": "echo consume",
            "input_file_ids": [file_id],
        },
    )

    # Initialize should create implicit dependency
    init_resp = await client.post(f"/workflows/{wf_id}/initialize")
    data = init_resp.json()
    assert data["ready_jobs"] == 1  # producer
    assert data["blocked_jobs"] == 1  # consumer blocked by producer
