"""Shared test fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from torcpy.server.orm import Base, make_engine, make_session_factory


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client(tmp_path) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with lifespan properly managed."""

    from fastapi import FastAPI

    from torcpy.server.api import (
        compute_nodes,
        events,
        failure_handlers,
        files,
        health,
        jobs,
        resource_requirements,
        results,
        schedulers,
        user_data,
        workflows,
    )
    from torcpy.server.background import BackgroundUnblockTask

    # Build a test app with manual setup (no lifespan needed)
    app = FastAPI()
    prefix = "/torcpy/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(workflows.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(files.router, prefix=prefix)
    app.include_router(user_data.router, prefix=prefix)
    app.include_router(resource_requirements.router, prefix=prefix)
    app.include_router(results.router, prefix=prefix)
    app.include_router(compute_nodes.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(failure_handlers.router, prefix=prefix)
    app.include_router(schedulers.local_router, prefix=prefix)
    app.include_router(schedulers.slurm_router, prefix=prefix)

    db_path = str(tmp_path / "test.db")
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = make_session_factory(engine)
    app.state.session_factory = session_factory

    bg_task = BackgroundUnblockTask(session_factory, interval=0.1)
    bg_task.start()
    app.state.bg_unblock = bg_task

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/torcpy/v1") as c:
        yield c

    await bg_task.stop()
    await engine.dispose()
