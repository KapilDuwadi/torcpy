"""File models."""

from pydantic import BaseModel


class FileCreate(BaseModel):
    workflow_id: int
    name: str
    path: str | None = None
    st_mtime: float | None = None


class FileUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    st_mtime: float | None = None


class File(BaseModel):
    id: int
    workflow_id: int
    name: str
    path: str | None = None
    st_mtime: float | None = None
