"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from torcpy.server.database import Database


def get_db(request: Request) -> Database:
    """Get database instance from app state."""
    return request.app.state.db  # type: ignore[no-any-return]
