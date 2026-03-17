"""User data API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.user_data import UserData, UserDataCreate, UserDataUpdate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/user_data", tags=["user_data"])


def _row_to_user_data(row: dict) -> UserData:
    data = row["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return UserData(
        id=row["id"],
        workflow_id=row["workflow_id"],
        name=row["name"],
        data=data,
        is_ephemeral=bool(row["is_ephemeral"]),
    )


@router.post("", status_code=201)
async def create_user_data(
    workflow_id: int, body: UserDataCreate, db: Database = Depends(get_db)
) -> UserData:
    uid = await db.insert(
        "INSERT INTO user_data (workflow_id, name, data, is_ephemeral) VALUES (?, ?, ?, ?)",
        (
            workflow_id,
            body.name,
            json.dumps(body.data) if body.data is not None else None,
            int(body.is_ephemeral),
        ),
    )
    row = await db.fetchone("SELECT * FROM user_data WHERE id = ?", (uid,))
    return _row_to_user_data(row)  # type: ignore[arg-type]


@router.get("")
async def list_user_data(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM user_data WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_user_data(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{user_data_id}")
async def get_user_data(
    workflow_id: int, user_data_id: int, db: Database = Depends(get_db)
) -> UserData:
    row = await db.fetchone(
        "SELECT * FROM user_data WHERE id = ? AND workflow_id = ?",
        (user_data_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"UserData {user_data_id} not found")
    return _row_to_user_data(row)


@router.patch("/{user_data_id}")
async def update_user_data(
    workflow_id: int,
    user_data_id: int,
    body: UserDataUpdate,
    db: Database = Depends(get_db),
) -> UserData:
    updates = []
    params: list = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.data is not None:
        updates.append("data = ?")
        params.append(json.dumps(body.data))
    if body.is_ephemeral is not None:
        updates.append("is_ephemeral = ?")
        params.append(int(body.is_ephemeral))
    if updates:
        params.extend([user_data_id, workflow_id])
        await db.execute(
            f"UPDATE user_data SET {', '.join(updates)} WHERE id = ? AND workflow_id = ?",
            tuple(params),
        )
        await db.conn.commit()
    return await get_user_data(workflow_id, user_data_id, db)


@router.delete("/{user_data_id}", status_code=204)
async def delete_user_data(
    workflow_id: int, user_data_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM user_data WHERE id = ? AND workflow_id = ?",
        (user_data_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"UserData {user_data_id} not found")
