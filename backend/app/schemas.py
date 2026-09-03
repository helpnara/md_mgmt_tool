from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    title: str
    status: str | None = None
    type: str | None = None
    group: str | None = None
    owners: list[str] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    # 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다.
    effect_expected: float | None = None
    effect_verified: float | None = None
    # 비우면 설정의 작성자를 쓴다 (로그인이 생기면 로그인 사용자).
    created_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    body: str | None = None


class ProjectUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    type: str | None = None
    group: str | None = None
    owners: list[str] | None = None
    start_date: str | None = None
    due_date: str | None = None
    effect_expected: float | None = None
    effect_verified: float | None = None
    tags: list[str] | None = None
    body: str | None = None

    def changes(self) -> dict[str, Any]:
        # 보내지 않은 항목만 건너뛴다. 보낸 값이 null 이면 그 항목을 비우겠다는 뜻이다
        # (효과 금액을 지우려면 이 구분이 반드시 필요하다).
        return self.model_dump(exclude_unset=True)


class EntryCreate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    author: str | None = None  # 비우면 설정의 작성자를 쓴다
    tags: list[str] = Field(default_factory=list)


class EntryUpdate(BaseModel):
    date: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None

    def changes(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
