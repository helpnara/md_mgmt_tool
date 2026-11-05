"""누가 무엇을 고쳤나 — 팀장 홈의 "팀원이 고친 것 — 최근 7일" (TODO 233 ⑥). 바깥(팀원 · 읽기)에는 막혀 있다(share.BLOCKED_PREFIXES)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import edits as svc

router = APIRouter(prefix="/api/edits", tags=["edits"])


@router.get("/recent")
def recent(conn: sqlite3.Connection = Depends(get_db), days: int = Query(7, ge=1, le=60)) -> dict:
    return {"days": days, "items": svc.recent(conn, days=days, role="member")}
