"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
from torcpy.server.database import Database

logger = logging.getLogger(__name__)


def create_app(db_path: str = "torcpy.db") -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup
        db = Database(db_path)
        await db.connect()
        await db.init_schema()
        app.state.db = db

        bg_task = BackgroundUnblockTask(db, interval=1.0)
        bg_task.start()
        app.state.bg_unblock = bg_task

        logger.info("TorcPy server started (db=%s)", db_path)
        yield

        # Shutdown
        await bg_task.stop()
        await db.close()
        logger.info("TorcPy server stopped")

    app = FastAPI(
        title="TorcPy",
        description="Distributed workflow orchestration",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount all API routers
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

    return app
