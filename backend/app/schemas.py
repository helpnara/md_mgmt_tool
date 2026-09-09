from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PartnerIn(BaseModel):
    """유관부서 한 줄 (TODO 92).

    `people` 은 `"김철수, 박민수"` 한 칸으로 와도 되고 목록으로 와도 된다 —
    나누는 일은 서비스가 맡는다(normalize_partners). 화면만 고쳐서는 API 를 직접
    부르는 길로 같은 사고가 다시 나기 때문이다 (TODO 74).
    """

    team: str
    people: list[str] | str = Field(default_factory=list)


class ProjectCreate(BaseModel):
    title: str
    status: str | None = None
    type: str | None = None
    group: str | None = None
    owners: list[str] = Field(default_factory=list)
    # 함께 일하는 팀과 그쪽 담당자. 팀도 여럿, 팀마다 사람도 여럿일 수 있다.
    partners: list[PartnerIn] = Field(default_factory=list)
    start_date: str | None = None
    due_date: str | None = None
    # 완료일 (TODO 104). 완료 상태로 만들면 오늘이 기본, 지난 과제면 손으로 적는다.
    completed_at: str | None = None
    # 과제 효과 (억원/년). 기대효과는 착수 시, 실증효과는 끝난 뒤 채운다.
    effect_expected: float | None = None
    effect_verified: float | None = None
    # 별도 보고가 필요 없는 과제 (단순 현황 관리). 보고 대상 후보에서만 빠진다.
    no_report: bool = False
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
    partners: list[PartnerIn] | None = None
    start_date: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    effect_expected: float | None = None
    effect_verified: float | None = None
    no_report: bool | None = None
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
