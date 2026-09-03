from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import settings as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    author: str | None = None
    # 과제 속성별 진행일지 서식. "" 키가 공통 서식이다.
    entry_templates: dict[str, str] | None = None
    # 보고 초안 서식. {summary} 자리에 미보고 진행일지가 들어간다.
    report_template: str | None = None
    # 과제 번호의 팀·부문 코드. 비우면 2026-001, "소재" 면 2026-소재-001.
    project_code: str | None = None


@router.get("")
def read_settings() -> dict:
    return svc.load()


@router.put("")
def update_settings(payload: SettingsUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "project_code" in changes:
        try:
            changes["project_code"] = svc.validate_project_code(changes["project_code"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 보내지 않은 항목은 건드리지 않는다.
    return svc.save(changes)


@router.get("/defaults")
def read_defaults() -> dict:
    """설정을 비웠을 때 쓰이는 기본 서식. 화면에서 안내 문구로 보여 준다."""
    from ..config import DEFAULT_ENTRY_TEMPLATE
    from ..services.reports import DRAFT_TEMPLATE

    return {"entry_template": DEFAULT_ENTRY_TEMPLATE, "report_template": DRAFT_TEMPLATE}
