"""쓰다 만 글 — 임시 보관 (TODO 170). 화면의 편집기가 쓰고, 홈이 모아 보인다."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import drafts as svc

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftIn(BaseModel):
    # 편집기마다 모양이 다르다 — 개요 · 보고 · 접수는 글 하나, 진행일지는 {date, title, body, tags}
    content: Any


def _check(key: str) -> None:
    if not svc.valid_key(key):
        raise HTTPException(status_code=400, detail="임시 보관 열쇠가 올바르지 않습니다.")


@router.get("")
def list_drafts(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"items": svc.listing(conn)}


@router.get("/{key}")
def get_draft(key: str) -> dict:
    """없으면 `content: null` — 편집기를 열 때마다 묻는 자리라 404 로 답하면 브라우저가 오류로 적는다."""
    _check(key)
    return svc.get(key) or {"key": key, "content": None, "updated_at": None}


@router.put("/{key}")
def put_draft(key: str, payload: DraftIn) -> dict:
    _check(key)
    try:
        record = svc.put(key, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"임시 보관을 쓰지 못했습니다: {exc}") from exc
    return {"key": key, "updated_at": record["updated_at"]}


@router.delete("/{key}", status_code=204)
def delete_draft(key: str) -> None:
    _check(key)
    svc.drop(key)
