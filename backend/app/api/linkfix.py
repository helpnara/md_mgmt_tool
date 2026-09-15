"""깨진 첨부 링크 정리 (TODO 116). 설정 → 점검의 [첨부 링크 정리] 칸이 쓴다."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_db
from ..services import linkfix as svc

router = APIRouter(prefix="/api/maintenance/link-fix", tags=["maintenance"])


class LinkFixRequest(BaseModel):
    include_frozen: bool = False


@router.get("")
def scan(include_frozen: bool = False, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """세기만 한다. 아무것도 바꾸지 않는다."""
    return svc.run(conn, apply=False, include_frozen=include_frozen)


@router.post("")
def apply(payload: LinkFixRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return svc.run(conn, apply=True, include_frozen=payload.include_frozen)
