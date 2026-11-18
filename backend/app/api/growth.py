"""개인 육성 목표 (TODO 292 C) — 팀장 · 관리자는 모두, 팀원은 자기 것을 보기만(쓰기는 permissions 가 막는다). 읽기 공유에는 막힘."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from .. import who
from ..services import team_plans as svc

router = APIRouter(prefix="/api/growth", tags=["growth"])


@router.get("")
def get_growth(request: Request, person: str = "", year: str = ""):
    user = who.of(request)
    if not user.manages:
        if user.role != who.MEMBER or not user.name:
            raise HTTPException(status_code=403, detail="육성 목표는 팀장과 본인만 봅니다.")
        person = user.name                     # 팀원 PC — 자기 것만
    if not person:
        raise HTTPException(status_code=400, detail="사람을 고르세요.")
    try:
        return svc.growth(person, year or None)
    except svc.PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.put("/{person}/{year}")
def put_growth(request: Request, person: str, year: str, goals: list[dict] = Body(..., embed=True)):
    user = who.of(request)
    if not user.manages:
        raise HTTPException(status_code=403, detail="육성 목표는 팀장이 적습니다 — 팀원은 보기만 합니다.")
    try:
        return svc.save_growth(person, year, goals, by=user.name or "팀장")
    except svc.PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
