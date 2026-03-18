"""SQLAlchemy async database layer."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 10_000
MAX_LIMIT = 10_000


def clamp_pagination(offset: int | None, limit: int | None) -> tuple[int, int]:
    """Clamp pagination parameters to valid ranges."""
    off = max(0, offset or 0)
    lim = min(MAX_LIMIT, max(1, limit or DEFAULT_LIMIT))
    return off, lim


@asynccontextmanager
async def write_transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Execute block inside BEGIN IMMEDIATE for write-concurrency safety."""
    await session.execute(text("BEGIN IMMEDIATE"))
    try:
        yield session
        await session.execute(text("COMMIT"))
    except Exception:
        await session.execute(text("ROLLBACK"))
        raise
