"""File API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.file import File, FileCreate, FileUpdate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/files", tags=["files"])


def _row_to_file(row: dict) -> File:
    return File(
        id=row["id"],
        workflow_id=row["workflow_id"],
        name=row["name"],
        path=row["path"],
        st_mtime=row["st_mtime"],
    )


@router.post("", status_code=201)
async def create_file(
    workflow_id: int, body: FileCreate, db: Database = Depends(get_db)
) -> File:
    fid = await db.insert(
        "INSERT INTO file (workflow_id, name, path, st_mtime) VALUES (?, ?, ?, ?)",
        (workflow_id, body.name, body.path, body.st_mtime),
    )
    row = await db.fetchone("SELECT * FROM file WHERE id = ?", (fid,))
    return _row_to_file(row)  # type: ignore[arg-type]


@router.get("")
async def list_files(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM file WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_file(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{file_id}")
async def get_file(
    workflow_id: int, file_id: int, db: Database = Depends(get_db)
) -> File:
    row = await db.fetchone(
        "SELECT * FROM file WHERE id = ? AND workflow_id = ?", (file_id, workflow_id)
    )
    if row is None:
        raise HTTPException(404, f"File {file_id} not found")
    return _row_to_file(row)


@router.patch("/{file_id}")
async def update_file(
    workflow_id: int, file_id: int, body: FileUpdate, db: Database = Depends(get_db)
) -> File:
    updates = []
    params: list = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.path is not None:
        updates.append("path = ?")
        params.append(body.path)
    if body.st_mtime is not None:
        updates.append("st_mtime = ?")
        params.append(body.st_mtime)
    if updates:
        params.extend([file_id, workflow_id])
        await db.execute(
            f"UPDATE file SET {', '.join(updates)} WHERE id = ? AND workflow_id = ?",
            tuple(params),
        )
        await db.conn.commit()
    return await get_file(workflow_id, file_id, db)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    workflow_id: int, file_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM file WHERE id = ? AND workflow_id = ?", (file_id, workflow_id)
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"File {file_id} not found")
