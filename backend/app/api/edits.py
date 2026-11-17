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


@router.get("/diff")
def diff(project: str, action: str, since: str = "", person: str = "", entry: int | None = None,
         first_at: str = "", last_at: str = "", base: str = "", conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """팀원이 고친 곳 (TODO 305) — 고치기 전 보관본 ↔ 지금. 팀장 홈 · 과제 화면이 부른다(바깥에는 막혀 있다)."""
    from ..services import edit_diff

    return edit_diff.diff(conn, project, entry, action, since, person, first_at, last_at, base)
