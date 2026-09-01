from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str
    status: str | None = None
    group: str | None = None
    owners: list[str] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    tags: list[str] = Field(default_factory=list)
    body: str | None = None


class ProjectUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    group: str | None = None
    owners: list[str] | None = None
    start_date: str | None = None
    due_date: str | None = None
    tags: list[str] | None = None
    body: str | None = None

    def changes(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class EntryCreate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] = Field(default_factory=list)


class EntryUpdate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None

    def changes(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
