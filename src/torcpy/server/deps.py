"""FastAPI dependency injection helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session from the app-level session factory."""
    async with request.app.state.session_factory() as session:
        yield session
