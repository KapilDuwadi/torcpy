"""Event models."""

from typing import Any

from pydantic import BaseModel


class EventCreate(BaseModel):
    workflow_id: int
    timestamp: int | None = None
    data: dict[str, Any] | None = None


class Event(BaseModel):
    id: int
    workflow_id: int
    timestamp: int | None = None
    data: dict[str, Any] | None = None
