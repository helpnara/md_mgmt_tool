from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import search as svc

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    q: str = Query("", description="검색어"), sort: str = Query("relevance", pattern="^(relevance|recent)$"),
    limit: int | None = Query(None, ge=1, le=50, description="갈래마다 몇 건까지 — 입력 중 미리보기(254 2차)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """여러 낱말 = 모두 · "구절" · -빼기 · 담당: 태그: 상태: 연도: 종류: (TODO 254). 과제는 관련도 순(sort=recent 면 최근 순).
    2차 — 띄어쓰기 무시 · 같은 말(역량 사전) · 초성(ㄱㅇㅅ)."""
    return svc.search(conn, q, limit=limit, sort=sort)
