from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..services import search as svc

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(
    q: str = Query("", description="검색어"), sort: str = Query("relevance", pattern="^(relevance|recent)$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """여러 낱말 = 모두 · "구절" · -빼기 · 담당: 태그: 상태: 연도: 종류: (TODO 254). 과제는 관련도 순(sort=recent 면 최근 순)."""
    return svc.search(conn, q, sort=sort)
