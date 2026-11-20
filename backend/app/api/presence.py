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


def _name(request: Request) -> str:
    user = who.of(request)
    return user.name or settings_service.current_author(None) or "팀장"


@router.post("/beat")
def beat(payload: BeatIn, request: Request) -> dict:
    return {"others": svc.beat(payload.target, payload.client, _name(request))}


@router.post("/leave", status_code=204)
def leave(payload: BeatIn) -> None:
    svc.leave(payload.target, payload.client)


@router.get("")
def listing(prefix: str = Query("", max_length=120), client: str = Query("", max_length=60)) -> dict:
    return {"items": svc.listing(prefix, client)}
