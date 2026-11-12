"""연말 회고 카드 (TODO 285) — 팀장 · 관리자만(share.BLOCKED_PREFIXES)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import who
from ..deps import get_db
from ..services import yearcards as svc

router = APIRouter(prefix="/api/yearcards", tags=["yearcards"])


class CardIn(BaseModel):
    message: str = ""
    headline: str = ""
    projects: list[str] = Field(default_factory=list)
    # 286 — 카드에서 다듬은 수행 · 결과 줄 {과제: {did: [..], result: [..]}} · 역량 · 보유 기술 3개씩(None 이면 자주 나온 순)
    lines: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    skills: list[str] | None = None
    tools: list[str] | None = None


def _manager(request: Request) -> None:
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="연말 카드는 팀장 · 관리자만 봅니다.")


@router.get("")
def listing(request: Request, year: str = Query(..., pattern=r"^\d{4}$"), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    return svc.listing(conn, year)


@router.get("/card")
def one(request: Request, name: str = Query(..., min_length=1, max_length=40), year: str = Query(..., pattern=r"^\d{4}$"),
        conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    return svc.card(conn, name, year)


@router.get("/cards")
def many(request: Request, year: str = Query(..., pattern=r"^\d{4}$"), names: str = Query(""), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """인쇄용 — 고른 사람들(쉼표로, 비우면 모두)의 카드."""
    _manager(request)
    wanted = [n.strip() for n in names.split(",") if n.strip()] or [p["name"] for p in svc.listing(conn, year)["people"]]
    return {"year": year, "cards": [svc.card(conn, name, year) for name in wanted]}


@router.put("/card")
def save(payload: CardIn, request: Request, name: str = Query(..., min_length=1, max_length=40),
         year: str = Query(..., pattern=r"^\d{4}$"), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    _manager(request)
    try:
        return svc.save(conn, name, year, payload.model_dump(), by=who.of(request).name or "")
    except svc.YearCardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
