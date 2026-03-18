"""File API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from torcpy.models.file import File, FileCreate, FileUpdate
from torcpy.server.database import clamp_pagination
from torcpy.server.deps import get_session
from torcpy.server.orm import FileORM

router = APIRouter(prefix="/workflows/{workflow_id}/files", tags=["files"])


def _orm_to_file(obj: FileORM) -> File:
    return File(
        id=obj.id,
        workflow_id=obj.workflow_id,
        name=obj.name,
        path=obj.path,
        st_mtime=obj.st_mtime,
    )


@router.post("", status_code=201)
async def create_file(
    workflow_id: int, body: FileCreate, session: AsyncSession = Depends(get_session)
) -> File:
    obj = FileORM(workflow_id=workflow_id, name=body.name, path=body.path, st_mtime=body.st_mtime)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _orm_to_file(obj)


@router.get("")
async def list_files(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    stmt = (
        select(FileORM)
        .where(FileORM.workflow_id == workflow_id)
        .order_by(FileORM.id)
        .offset(off)
        .limit(lim + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > lim
    return {
        "items": [_orm_to_file(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{file_id}")
async def get_file(
    workflow_id: int, file_id: int, session: AsyncSession = Depends(get_session)
) -> File:
    stmt = select(FileORM).where(FileORM.id == file_id, FileORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"File {file_id} not found")
    return _orm_to_file(obj)


@router.patch("/{file_id}")
async def update_file(
    workflow_id: int,
    file_id: int,
    body: FileUpdate,
    session: AsyncSession = Depends(get_session),
) -> File:
    stmt = select(FileORM).where(FileORM.id == file_id, FileORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"File {file_id} not found")
    if body.name is not None:
        obj.name = body.name
    if body.path is not None:
        obj.path = body.path
    if body.st_mtime is not None:
        obj.st_mtime = body.st_mtime
    await session.commit()
    await session.refresh(obj)
    return _orm_to_file(obj)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    workflow_id: int, file_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    stmt = select(FileORM).where(FileORM.id == file_id, FileORM.workflow_id == workflow_id)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"File {file_id} not found")
    await session.delete(obj)
    await session.commit()
