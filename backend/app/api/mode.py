"""체험 자료 · 내 자료 모드 (TODO 295) — 보기는 누구나(체험 띠 · 팀원 PC 안내), 바꾸기는 관리자(서버 PC)만."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import who
from ..services import mode as svc

router = APIRouter(prefix="/api/mode", tags=["mode"])


class SwitchIn(BaseModel):
    mode: str
    mine_dir: str | None = None
    reset: bool = False


@router.get("")
def status() -> dict:
    return svc.status()


@router.post("")
def switch(payload: SwitchIn, request: Request) -> dict:
    if who.of(request).role != who.OWNER:
        raise HTTPException(status_code=403, detail="체험 · 내 자료 바꾸기는 서버 PC(관리자)에서만 합니다.")
    try:
        return svc.start(payload.mode, payload.mine_dir, payload.reset)
    except svc.ModeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
