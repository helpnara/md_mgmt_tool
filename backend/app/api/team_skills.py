"""팀 역량 · 기술 스택 (TODO 284) — 팀장 · 관리자만."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from .. import who
from ..deps import get_db
from ..services import settings as settings_service
from ..services import team_skills as svc

router = APIRouter(prefix="/api/team-skills", tags=["team-skills"])


@router.get("")
def overview(request: Request, period: str = Query("3y", pattern="^(3y|year|all)$"), left: bool = False, conn=Depends(get_db)):
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    return svc.overview(conn, period, left)


@router.put("/targets")
def save_targets(request: Request, targets: list[dict] = Body(..., embed=True)):
    """목표 역량 · 보유 기술 (TODO 284 2단계) — 설정 `team_skill_targets`. 팀장 PC 에서도 저장한다(설정 화면은 서버 PC 만)."""
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    try:
        settings_service.save({"team_skill_targets": targets})
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    return {"targets": settings_service.load().get("team_skill_targets") or []}

