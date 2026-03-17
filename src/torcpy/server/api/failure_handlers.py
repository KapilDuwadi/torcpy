"""Failure handler API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from torcpy.models.failure_handler import FailureHandler, FailureHandlerCreate
from torcpy.server.database import Database, clamp_pagination
from torcpy.server.deps import get_db

router = APIRouter(
    prefix="/workflows/{workflow_id}/failure_handlers", tags=["failure_handlers"]
)


def _row_to_fh(row: dict) -> FailureHandler:
    rules = row["rules"]
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            rules = []
    return FailureHandler(
        id=row["id"],
        workflow_id=row["workflow_id"],
        name=row["name"],
        rules=rules or [],
        default_max_retries=row["default_max_retries"],
        default_recovery_command=row["default_recovery_command"],
    )


@router.post("", status_code=201)
async def create_failure_handler(
    workflow_id: int,
    body: FailureHandlerCreate,
    db: Database = Depends(get_db),
) -> FailureHandler:
    fhid = await db.insert(
        """
        INSERT INTO failure_handler (workflow_id, name, rules, default_max_retries,
            default_recovery_command)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            body.name,
            json.dumps([r.model_dump() for r in body.rules]),
            body.default_max_retries,
            body.default_recovery_command,
        ),
    )
    row = await db.fetchone("SELECT * FROM failure_handler WHERE id = ?", (fhid,))
    return _row_to_fh(row)  # type: ignore[arg-type]


@router.get("")
async def list_failure_handlers(
    workflow_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    db: Database = Depends(get_db),
) -> dict:
    off, lim = clamp_pagination(offset, limit)
    rows = await db.fetchall(
        "SELECT * FROM failure_handler WHERE workflow_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (workflow_id, lim + 1, off),
    )
    has_more = len(rows) > lim
    return {
        "items": [_row_to_fh(r) for r in rows[:lim]],
        "offset": off,
        "limit": lim,
        "has_more": has_more,
    }


@router.get("/{fh_id}")
async def get_failure_handler(
    workflow_id: int, fh_id: int, db: Database = Depends(get_db)
) -> FailureHandler:
    row = await db.fetchone(
        "SELECT * FROM failure_handler WHERE id = ? AND workflow_id = ?",
        (fh_id, workflow_id),
    )
    if row is None:
        raise HTTPException(404, f"FailureHandler {fh_id} not found")
    return _row_to_fh(row)


@router.delete("/{fh_id}", status_code=204)
async def delete_failure_handler(
    workflow_id: int, fh_id: int, db: Database = Depends(get_db)
) -> None:
    result = await db.execute(
        "DELETE FROM failure_handler WHERE id = ? AND workflow_id = ?",
        (fh_id, workflow_id),
    )
    await db.conn.commit()
    if result.rowcount == 0:
        raise HTTPException(404, f"FailureHandler {fh_id} not found")
