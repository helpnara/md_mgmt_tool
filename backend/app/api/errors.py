"""오류 기록 보기. 설정 화면의 [최근 오류] 칸이 쓴다."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import errorlog as svc

router = APIRouter(prefix="/api/errors", tags=["errors"])


@router.get("")
def list_errors(limit: int = Query(svc.RECENT_LIMIT, ge=1, le=200)) -> dict:
    return {"items": svc.recent(limit), "keep_months": svc.KEEP_MONTHS}


@router.delete("")
def clear_errors() -> dict:
    """기록을 비운다. 문제를 재현하기 전에 눌러 두면 그 뒤의 것만 남는다."""
    return {"removed_files": svc.clear()}
