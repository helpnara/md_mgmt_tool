"""쓰다 만 글 — 임시 보관 (TODO 170). 화면의 편집기가 쓰고, 홈이 모아 보인다."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..deps import get_db
from ..services import drafts as svc
from .. import who

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftIn(BaseModel):
    # 편집기마다 모양이 다르다 — 개요 · 보고 · 접수는 글 하나, 진행일지는 {date, title, body, tags}
    content: Any


def _check(key: str) -> None:
    if not svc.valid_key(key):
        raise HTTPException(status_code=400, detail="임시 보관 열쇠가 올바르지 않습니다.")


def _person(request: Request) -> str | None:
    """팀원 PC 에서 온 요청이면 그 사람의 폴더 (TODO 233 R8). 팀장은 지금 자리 그대로."""
    user = who.of(request)
    return user.name if user.role == who.MEMBER else None


@router.get("")
def list_drafts(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"items": svc.listing(conn, _person(request))}


@router.get("/{key}")
def get_draft(key: str, request: Request) -> dict:
    """없으면 `content: null` — 편집기를 열 때마다 묻는 자리라 404 로 답하면 브라우저가 오류로 적는다."""
    _check(key)
    return svc.get(key, _person(request)) or {"key": key, "content": None, "updated_at": None}


@router.put("/{key}")
def put_draft(key: str, payload: DraftIn, request: Request) -> dict:
    _check(key)
    try:
        record = svc.put(key, payload.content, _person(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"임시 보관을 쓰지 못했습니다: {exc}") from exc
    return {"key": key, "updated_at": record["updated_at"]}


@router.delete("/{key}", status_code=204)
def delete_draft(key: str, request: Request) -> None:
    _check(key)
    svc.drop(key, _person(request))
