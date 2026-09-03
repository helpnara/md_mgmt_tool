from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import renumber as renumber_svc
from ..services import settings as svc
from ..vault.paths import FileInUseError

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


class RenumberRequest(BaseModel):
    """과제 번호를 새 팀 코드로 한 번에 맞춘다."""

    code: str


@router.post("/project-code/renumber/preview")
def preview_renumber(
    payload: RenumberRequest, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """무엇이 어떻게 바뀌는지만 돌려준다. 파일은 건드리지 않는다."""
    try:
        return renumber_svc.plan(conn, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/project-code/renumber")
def run_renumber(payload: RenumberRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """미리보기대로 실제로 바꾸고, 설정의 팀 코드도 함께 맞춘다."""
    try:
        result = renumber_svc.apply(conn, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # 번호를 바꿔 놓고 설정이 예전 코드면 다음에 만드는 과제가 또 어긋난다.
    svc.save({"project_code": result["code"]})
    return result
