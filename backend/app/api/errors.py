"""오류 기록 보기. 설정 화면의 [최근 오류] 칸이 쓴다."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..services import errorlog as svc

router = APIRouter(prefix="/api/errors", tags=["errors"])


@router.get("")
def list_errors(limit: int = Query(svc.RECENT_LIMIT, ge=1, le=200)) -> dict:
    return {"items": svc.recent(limit), "keep_months": svc.KEEP_MONTHS}


@router.delete("")
def clear_errors() -> dict:
    """기록을 비운다. 문제를 재현하기 전에 눌러 두면 그 뒤의 것만 남는다."""
    return {"removed_files": svc.clear()}


class ClientError(BaseModel):
    """화면 쪽 오류 한 건 (TODO 166). **과제 내용은 받지 않는다** — 어느 화면에서 · 무엇이 · 왜."""

    screen: str = Field("", max_length=80)
    kind: str = Field("", max_length=40)
    message: str = Field("", max_length=300)


@router.post("/client", status_code=204)
def record_client_error(payload: ClientError) -> None:
    """화면이 그리다 멈추거나 처리 안 된 실패가 남았을 때 — 서버 오류만 남던 기록에 함께 쌓는다.

    전에는 화면 쪽 결함은 브라우저 안쪽(콘솔)에만 남아, 사용자가 "화면이 하얘졌다" 고 말해도 근거가
    없었다. 상태는 비워 두고(`status: None` → 화면에 "화면" 으로 보인다) 동작 자리에 화면 이름을 적는다.
    """
    svc.record(
        action=f"화면 {payload.screen or '?'}",
        status=None,
        error=payload.kind or "ClientError",
        detail=payload.message or None,
    )
