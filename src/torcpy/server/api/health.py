"""Health check endpoints."""

from fastapi import APIRouter

from torcpy import __version__

router = APIRouter(tags=["health"])


@router.get("/ping")
async def ping() -> dict:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    return {"version": __version__}
