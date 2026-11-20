"""지금 고치는 중 (TODO 317) — 편집기가 15초마다 알리고, 과제 화면이 모아 본다."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from .. import who
from ..services import presence as svc
from ..services import settings as settings_service

router = APIRouter(prefix="/api/presence", tags=["presence"])


class BeatIn(BaseModel):
    target: str = Field(min_length=1, max_length=120)
    client: str = Field(min_length=4, max_length=60)
    idle: float = 0.0          # 318 — 마지막 입력 뒤 지난 초


def _name(request: Request) -> str:
    user = who.of(request)
    return user.name or settings_service.current_author(None) or "팀장"


@router.post("/beat")
def beat(payload: BeatIn, request: Request) -> dict:
    others = svc.beat(payload.target, payload.client, _name(request), payload.idle)
    return {"others": others, "holder": svc.holder(payload.target, payload.client)}


@router.post("/leave", status_code=204)
def leave(payload: BeatIn) -> None:
    svc.leave(payload.target, payload.client)


@router.get("")
def listing(prefix: str = Query("", max_length=120), client: str = Query("", max_length=60)) -> dict:
    return {"items": svc.listing(prefix, client)}


@router.get("/lock")
def lock(target: str = Query(..., min_length=1, max_length=120), client: str = Query("", max_length=60)) -> dict:
    """318 — [수정]을 누르기 전에: 다른 사람이 먼저 고치는 중인가(부드러운 잠금)."""
    return {"holder": svc.holder(target, client)}

