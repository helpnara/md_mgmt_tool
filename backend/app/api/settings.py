from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import settings as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    author: str | None = None
    # 과제 속성별 진행일지 서식. "" 키가 공통 서식이다.
    entry_templates: dict[str, str] | None = None
    # 보고 초안 서식. {summary} 자리에 미보고 진행일지가 들어간다.
    report_template: str | None = None


@router.get("")
def read_settings() -> dict:
    return svc.load()


@router.put("")
def update_settings(payload: SettingsUpdate) -> dict:
    # 보내지 않은 항목은 건드리지 않는다.
    return svc.save(payload.model_dump(exclude_unset=True))


@router.get("/defaults")
def read_defaults() -> dict:
    """설정을 비웠을 때 쓰이는 기본 서식. 화면에서 안내 문구로 보여 준다."""
    from ..config import DEFAULT_ENTRY_TEMPLATE
    from ..services.reports import DRAFT_TEMPLATE

    return {"entry_template": DEFAULT_ENTRY_TEMPLATE, "report_template": DRAFT_TEMPLATE}
