"""사람별 이력 (TODO 238 ①) — 한 사람이 맡은(지금 · 예전) 과제를 연도별로, 역할 · 담당 기간 · 회고 · 성과와 교육 · 행사 이력.

`/api/people` 아래에 두지 않는다 — 명부(사번)는 바깥에 막혀 있지만(share.BLOCKED_PREFIXES) 이 화면은 누구나 본다(238-3).
여기 실리는 것은 과제 상세 · 팀원역량에서 이미 보이는 것뿐이고, 면담은 넣지 않는다.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..deps import get_db
from ..services import person_history as svc

router = APIRouter(prefix="/api/person-history", tags=["people"])


@router.get("/year")
def year_review(name: str = Query(..., min_length=1, max_length=40), year: str = Query(..., pattern=r"^\d{4}$"),
                conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """나의 한 해 (TODO 244 A3) — 누구나(이력 화면과 같다). 인정 한 줄 · 면담은 넣지 않는다."""
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status_code=400, detail="사람 이름이 비어 있습니다.")
    return svc.year_review(conn, name, year)


@router.get("")
def person_history(request: Request, name: str = Query(..., min_length=1, max_length=40),
                   conn: sqlite3.Connection = Depends(get_db)) -> dict:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status_code=400, detail="사람 이름이 비어 있습니다.")
    data = svc.history(conn, name)
    # 팀장의 인정 한 줄 (TODO 242 A2) — 그 사람과 팀장만
    from .. import who
    from .projects import hide_praise

    data["projects"] = hide_praise([{**item, "name": name} for item in data["projects"]], who.of(request))
    return data
