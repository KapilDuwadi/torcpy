"""User data models."""

from typing import Any

from pydantic import BaseModel


class UserDataCreate(BaseModel):
    workflow_id: int
    name: str
    data: Any = None
    is_ephemeral: bool = False


class UserDataUpdate(BaseModel):
    name: str | None = None
    data: Any = None
    is_ephemeral: bool | None = None


class UserData(BaseModel):
    id: int
    workflow_id: int
    name: str
    data: Any = None
    is_ephemeral: bool = False
