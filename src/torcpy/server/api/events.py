"""Event API endpoints."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.event import Event, EventCreate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(prefix="/workflows/{workflow_id}/events", tags=["events"])


def _row_to_event(row: dict) -> Event:
    data = row["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return Event(
        id=row["id"],
        workflow_id=row["workflow_id"],
        timestamp=row["timestamp"],
        data=data,
    )


@router.post("", status_code=201)
async def create_event(
    workflow_id: int, body: EventCreate, db: Database = Depends(get_db)
) -> Event:
    ts = body.timestamp or int(time.time())
    eid = await db.insert(
        "INSERT INTO event (workflow_id, timestamp, data) VALUES (?, ?, ?)",
        (workflow_id, ts, json.dumps(body.data) if body.data else None),
    )
    row = await db.fetchone("SELECT * FROM event WHERE id = ?", (eid,))
    return _row_to_event(row)  # type: ignore[arg-type]


@router.get("")
async def list_events(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM event WHERE workflow_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_event(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{event_id}")
async def get_event(
    workflow_id: int, event_id: int, db: Database = Depends(get_db)
) -> Event:
    row = await db.fetchone(
        "SELECT * FROM event WHERE id = ? AND workflow_id = ?",
        (event_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"Event {event_id} not found")
    return _row_to_event(row)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    workflow_id: int, event_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM event WHERE id = ? AND workflow_id = ?",
        (event_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"Event {event_id} not found")
