"""Tests for workflow API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_workflow(client: AsyncClient):
    resp = await client.post("/workflows", json={"name": "test-wf", "user": "tester"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-wf"
    assert data["user"] == "tester"
    assert data["id"] > 0


@pytest.mark.asyncio
async def test_list_workflows(client: AsyncClient):
    await client.post("/workflows", json={"name": "wf1"})
    await client.post("/workflows", json={"name": "wf2"})
    resp = await client.get("/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_get_workflow(client: AsyncClient):
    create_resp = await client.post("/workflows", json={"name": "get-test"})
    wf_id = create_resp.json()["id"]

    resp = await client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-test"


@pytest.mark.asyncio
async def test_get_workflow_not_found(client: AsyncClient):
    resp = await client.get("/workflows/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_workflow(client: AsyncClient):
    create_resp = await client.post("/workflows", json={"name": "to-delete"})
    wf_id = create_resp.json()["id"]

    resp = await client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_workflow(client: AsyncClient):
    create_resp = await client.post("/workflows", json={"name": "to-cancel"})
    wf_id = create_resp.json()["id"]

    resp = await client.post(f"/workflows/{wf_id}/cancel")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_workflow_status(client: AsyncClient):
    create_resp = await client.post("/workflows", json={"name": "status-test"})
    wf_id = create_resp.json()["id"]

    resp = await client.get(f"/workflows/{wf_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == wf_id
    assert data["total_jobs"] == 0
