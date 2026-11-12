"""팀 역량 · 기술 스택 (TODO 284) — 팀장 · 관리자만."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import who
from ..deps import get_db
from ..services import team_skills as svc

router = APIRouter(prefix="/api/team-skills", tags=["team-skills"])


@router.get("")
def overview(request: Request, period: str = Query("3y", pattern="^(3y|year|all)$"), left: bool = False, conn=Depends(get_db)):
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    return svc.overview(conn, period, left)
